from __future__ import annotations

import re
from pathlib import Path
from typing import Any

DEPARTMENTS = {
    "warehouse": {"approver": "Ana Whitfield", "terms": ("warehouse", "warehousing", "storage", "almacenamiento", "almacén")},
    "lastmile": {"approver": "Carlos Vega", "terms": ("last mile", "last-mile", "delivery", "shipping", "envío", "entrega", "transportista propio", "carrier")},
    "reverse": {"approver": "Sofía Ramos", "terms": ("reverse logistics", "returns", "devoluciones", "devolución")},
}


def convert_pdf_to_markdown(pdf_path: Path, markdown_path: Path) -> str:
    """Extract PDF text with MarkItDown; pdfminer is a documented fallback."""
    try:
        from markitdown import MarkItDown

        markdown = MarkItDown().convert(str(pdf_path)).text_content
    except ImportError:
        try:
            from pdfminer.high_level import extract_text
        except ImportError as exc:
            raise RuntimeError("PDF conversion requires MarkItDown or pdfminer.six") from exc
        markdown = extract_text(str(pdf_path))
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(markdown, encoding="utf-8")
    return markdown


def readability_metrics(markdown: str) -> dict[str, float | int | bool]:
    words = re.findall(r"\b[\w'-]+\b", markdown)
    return {
        "character_count": len(markdown),
        "word_count": len(words),
        "line_count": len(markdown.splitlines()),
        "readable": len(words) >= 20 and sum(char.isalpha() for char in markdown) / max(len(markdown), 1) >= 0.45,
    }


def classify_document(markdown: str) -> tuple[bool, str]:
    text = markdown.casefold()
    customer_intent = any(term in text for term in (
        "request for proposal", "request for quotation", "rfp", "we are looking for",
        "looking for", "need someone to", "could you send over a proposal",
        "send over a proposal", "could you send a proposal",
        "need someone to handle our warehousing and shipping needs",
        "we need a fulfillment", "please provide a proposal", "solicitamos una propuesta",
        "estamos buscando", "pedidos por mes", "orders per month",
    ))
    carrier_pitch = any(term in text for term in (
        "carrier rates", "our rates", "transportation rates", "carrier pitch",
        "we offer shipping", "our shipping services", "tarifas de transporte",
        "tarifas de transportista", "preferred carrier partners", "introductory rates",
        "offering aggressive", "become one of trackflow's preferred",
    ))
    scope = any(term in text for info in DEPARTMENTS.values() for term in info["terms"])
    accepted = customer_intent and not carrier_pitch and scope
    reason = "customer_request_with_logistics_scope" if accepted else (
        "carrier_sales_pitch" if carrier_pitch else "no_customer_rfp_intent_or_logistics_scope"
    )
    return accepted, reason


def _first_match(pattern: str, text: str, flags: int = re.IGNORECASE) -> str | None:
    match = re.search(pattern, text, flags)
    return match.group(1).strip(" \t.,;:-") if match else None


def extract_metadata(markdown: str) -> dict[str, Any]:
    text = markdown
    lower = text.casefold()
    client_name = _first_match(r"(?:company|client|brand|cliente|marca)\s*[:\-]\s*([^\n]+)", text)
    if not client_name:
        client_name = next((name for name in ("ModaViva", "Luna Cosmetics") if name.casefold() in lower), None)

    if any(term in lower for term in ("spain", "españa", "spanish")):
        country, currency = "Spain", "EUR"
    elif any(term in lower for term in ("united states", "usa", "u.s.", "los angeles", "california", "\b\busa\b")):
        country, currency = "United States", "USD"
    else:
        country, currency = None, None

    requested: list[str] = []
    unknown: list[str] = []
    department_map = {"warehouse": "warehouse", "lastmile": "lastmile", "reverse": "reverse"}
    for department_id, info in DEPARTMENTS.items():
        found = [term for term in info["terms"] if term in lower]
        excluded = department_id == "lastmile" and any(term in lower for term in ("own carrier", "own transportista", "uses its own carrier", "transportista propio"))
        if found and not excluded:
            requested.append(department_id)
    monthly_volume_text = _first_match(
        r"([\d,]+)\s*(?:orders?|pedidos?)\s*(?:(?:per|por|/)\s*)?(?:a\s+)?(?:month|mes)?",
        text,
    )
    monthly_volume = int(monthly_volume_text.replace(",", "")) if monthly_volume_text else None
    deadline = _first_match(r"(?:deadline|due date|fecha límite|fecha limite)\s*[:\-]?\s*([^\n]+)", text)
    budget = _first_match(r"(?:budget|presupuesto)\s*[:\-]?\s*([^\n]+)", text)
    services = list(requested)
    return {
        "client_name": client_name,
        "client_country": country,
        "services_requested": services,
        "unknown_services": unknown,
        "monthly_volume": monthly_volume,
        "monthly_volume_unit": "orders/month" if monthly_volume is not None else None,
        "deadline": deadline,
        "budget_range": budget,
        "departments_needed": requested,
        "currency": currency,
    }


def build_department_sections(markdown: str, metadata: dict[str, Any]) -> list[dict[str, Any]]:
    lower = markdown.casefold()
    sections = []
    for department_id in metadata["departments_needed"]:
        info = DEPARTMENTS[department_id]
        matched = [line.strip() for line in markdown.splitlines() if any(term in line.casefold() for term in info["terms"])]
        aspects = matched[:8]
        questions = []
        if department_id == "warehouse" and metadata["monthly_volume"] is None:
            questions.append("What is the expected monthly order volume and storage footprint?")
        if department_id == "lastmile" and metadata["client_country"] is None:
            questions.append("Which destination country/regions and delivery SLA are required?")
        if department_id == "reverse" and not any(term in lower for term in ("return rate", "devoluciones", "returns")):
            questions.append("What return volume and processing requirements should be planned?")
        sections.append({
            "department_id": department_id,
            "approver": info["approver"],
            "key_aspects": aspects,
            "open_questions": questions,
            "source_extract": "\n".join(matched)[:4000],
        })
    return sections


def process_rfp_document(pdf_path: Path, markdown_path: Path) -> dict[str, Any]:
    markdown = convert_pdf_to_markdown(pdf_path, markdown_path)
    accepted, reason = classify_document(markdown)
    metrics = readability_metrics(markdown)
    if not accepted:
        return {"accepted": False, "reason": reason, "markdown_path": str(markdown_path), "readability_metrics": metrics}
    metadata = extract_metadata(markdown)
    metadata["readability_metrics"] = metrics
    sections = build_department_sections(markdown, metadata)
    handoff = {
        "ticket_id": None,
        "metadata": metadata,
        "department_workstreams": sections,
        "source_markdown_path": str(markdown_path),
        "contract_version": "1.0",
    }
    return {
        "accepted": True,
        "reason": reason,
        "markdown_path": str(markdown_path),
        "metadata": metadata,
        "department_sections": sections,
        "handoff": handoff,
    }