"""Local routing keeps operational records out of external model requests."""

import re
import unicodedata
from typing import Literal, TypedDict

from services.support_agent.incidents import IncidentQuery


class RoutingDecision(TypedDict):
    source: Literal["rag", "incidents", "both"]
    query: IncidentQuery | None


def normalized_question(question: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", question.casefold())
        if not unicodedata.combining(char)
    )


def decide_sources(question: str) -> RoutingDecision:
    text = normalized_question(question)
    reference_groups = re.findall(
        r"\b(?:tickets?|incidencias?|incidents?)\s*(?:id\s*|numero\s*|n[º°]\s*)?"
        r"[#:]?\s*(\d+(?:\s*(?:,|y|and)\s*\d+)*)\b",
        text,
    )
    references = [number for group in reference_groups for number in re.findall(r"\d+", group)]
    incident_topic = bool(re.search(r"\b(?:tickets?|incidencias?|incidents?)\b", text))
    knowledge = bool(re.search(
        r"\b(?:politicas?|policy|procedimientos?|procedures?|protocolo|"
        r"por que|why|que (?:debo|debemos|hacer|significa)|pasos|"
        r"significado|meaning|definicion|"
        r"como (?:gestionar|resolver|tramitar|proceder|funcionan)|"
        r"how (?:to|should))\b", text,
    ))
    lookup_request = bool(re.search(
        r"\b(?:actual|current|lista|list|listar|muestra|show|busca|buscar|search|"
        r"find|consulta|consultar|ver|dame|cuantas|cuantos|how many)\b", text,
    ))
    operational = bool(references) or (
        incident_topic and (lookup_request or (not knowledge and bool(re.search(
            r"\b(?:estado|status|abiert[ao]s?|open|"
            r"pendientes?|resuelt[ao]s?|resolved|descartad[ao]s?|discarded)\b",
            text,
        ))))
    )
    if not operational:
        return {"source": "rag", "query": None}
    source: Literal["incidents", "both"] = "both" if knowledge else "incidents"
    ids = set(references)
    if len(ids) > 1 or (ids and int(next(iter(ids))) <= 0):
        return {"source": source, "query": None}
    if ids:
        return {"source": source, "query": IncidentQuery(ticket_id=int(next(iter(ids))))}
    if re.search(r"\b(?:ticket|incidencia|incident)\b", text):
        return {"source": source, "query": None}
    filters: dict[str, str] = {}
    for field, options in {
        "status": {
            "open": r"\b(?:open|abiert[ao]s?)\b",
            "in_progress": r"\b(?:in_progress|en progreso|pendientes?)\b",
            "resolved": r"\b(?:resolved|resuelt[ao]s?|cerrad[ao]s?)\b",
            "discarded": r"\b(?:discarded|descartad[ao]s?)\b",
        },
        "branch": {
            "zaragoza": r"\bzaragoza\b",
            "los-angeles": r"\blos[ -]angeles\b",
            "central": r"\bcentral\b",
        },
        "category": {
            "tracking": r"\btracking\b",
            "devolucion": r"\bdevolucion(?:es)?\b",
            "facturacion": r"\bfacturacion\b",
            "logistica": r"\blogistica\b",
            "soporte": r"\bsoporte\b",
        },
        "origin": {
            "customer": r"\b(?:customer|clientes?)\b",
            "branch": r"\b(?:origin|origen)\s+(?:branch|sede)\b",
            "internal": r"\b(?:internal|intern[ao]s?)\b",
        },
    }.items():
        matches = [value for value, pattern in options.items() if re.search(pattern, text)]
        if len(matches) > 1:
            return {"source": source, "query": None}
        if matches:
            filters[field] = matches[0]
    return {"source": source, "query": IncidentQuery.model_validate(filters)}
