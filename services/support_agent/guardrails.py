"""Deterministic input/output guards for the TrackFlow CX agent."""

import logging
import re
import unicodedata
from collections import Counter
from threading import RLock
from typing import Literal, TypedDict

logger = logging.getLogger("trackflow_api.support_agent.guardrails")

FailureCategory = Literal["security", "content", "structural", "redirect"]


class InputDecision(TypedDict):
    action: Literal["allow", "reject", "redirect"]
    answer: str | None
    country: Literal["US", "ES"] | None
    guardrail: str | None
    category: FailureCategory | None


_lock = RLock()
_counts: Counter[str] = Counter()


def record_guardrail(name: str, category: FailureCategory) -> None:
    """Count and log a guardrail activation without logging user data."""
    with _lock:
        _counts[name] += 1
    logger.warning("Guardrail activated name=%s category=%s", name, category)


def guardrail_summary() -> dict[str, int]:
    with _lock:
        return dict(sorted(_counts.items()))


def reset_guardrail_summary() -> None:
    """Reset process-local counters; intended for isolated test sessions."""
    with _lock:
        _counts.clear()


_JAILBREAK_PATTERNS = (
    r"\bignore\s+(?:all\s+)?(?:your\s+)?(?:previous|prior|above)\s+instructions\b",
    r"\bignora\s+(?:todas\s+)?(?:tus\s+)?instrucciones\b",
    r"\b(?:act|behave)\s+as\s+(?:an?\s+)?(?:assistant|ai)\s+(?:with\s+)?no\s+rules\b",
    r"\b(?:ahora\s+)?eres\s+(?:un\s+)?asistente\s+sin\s+reglas\b",
    r"\bforget\s+(?:that\s+)?you\s+work\s+for\s+trackflow\b",
    r"\bolvida\s+(?:que\s+)?trabajas\s+para\s+trackflow\b",
    r"\bolvidate\s+de\s+trackflow\b.{0,60}\b(?:obedece|obey|sigue|follow)\b.{0,40}\b(?:nuevas\s+)?(?:reglas|instrucciones)\b",
    r"\b(?:reveal|show|print|repeat|repite|revela|muestra)\b.{0,50}\b(?:system\s+prompt|instrucciones\s+internas|prompt\s+del\s+sistema)\b",
    r"\b(?:override|bypass|anula|cambia|sustituye)\b.{0,50}\b(?:system|instrucciones|guardrails|reglas)\b",
)
_PERSONAL_PATTERNS = (
    r"\b(?:write|escribe|redacta|ayudame a escribir|hazme)\b.{0,60}\b(?:essay|ensayo|poem|poema|homework|tarea|code|codigo)\b",
    r"\b(?:ayudame|help me)\b.{0,40}\b(?:write|escribir|essay|ensayo|poem|poema|homework|tarea|code|codigo)\b",
    r"\b(?:actua como|haz de|be my|make yourself)\b.{0,40}\b(?:therapist|terapeuta|personal assistant|asistente personal)\b",
    r"\b(?:consejo personal|personal advice|mi relacion|my relationship)\b",
)
_DOMAIN_TERMS = re.compile(
    r"\b(?:trackflow|tracking|seguimiento|envio|envios|paquete|pedido|ticket|tickets|devolucion|"
    r"incidencia|incidencias|entrega|direccion incorrecta|carrier|transportista|"
    r"logistica|logistics|sla|lost package|failed delivery|return)\b", re.I,
)
_DOMAIN_POLICY_QUESTION = re.compile(
    r"\b(?:politica|policy|devolucion|devoluciones|returns?)\b", re.I,
)
_CASUAL_PATTERNS = (
    r"\b(?:hola|buenos dias|buenas tardes|buenas noches|hi|hello|thanks|gracias)\b",
    r"\b(?:que hora es|what time is it)\b",
    r"\b(?:como estas|how are you)\b",
    r"\b(?:que hora es|what time is it)\b.{0,40}\b(?:tokio|tokyo)\b",
)
_ORDER_REFERENCE = re.compile(
    r"\b(?:pedido|orden|order|tracking|seguimiento)\s*(?:n(?:umero|o)?\.?\s*)?(?:#|:)?\s*([a-z0-9-]*\d[a-z0-9-]*)\b",
    re.I,
)
_MEMORY_COMMAND = re.compile(
    r"^(?P<command>aprobar|rechazar|editar|edita|editar propuesta|edita propuesta)"
    r"(?:\s*[,;:]\s*|\s+)(?P<remainder>.+)$|"
    r"^(?P<standalone>aprobar|rechazar)$",
    re.I,
)
_MEMORY_DECISION_REMAINDER = re.compile(
    r"^(?:no\s+(?:la|lo)\s+guardes|no\s+estoy\s+segur[oa]|"
    r"rechazar|rechazo|descarto|no\s+lo\s+recuerdes)$",
    re.I,
)


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def classify_input(question: str, *, allow_memory_command: bool = False) -> InputDecision:
    """Fail closed on instruction attacks, personal requests and tracking access."""
    text = question.strip()
    normalized_text = _normalize(text)
    if not normalized_text:
        # Let the graph produce its established invalid_question trace/HTTP 422.
        return {"action": "allow", "answer": None, "country": None, "guardrail": None, "category": None}
    memory_command = _MEMORY_COMMAND.fullmatch(normalized_text) if allow_memory_command else None
    if memory_command:
        remainder = memory_command.group("remainder") or ""
        if not remainder or _MEMORY_DECISION_REMAINDER.fullmatch(remainder.strip()):
            return {"action": "allow", "answer": None, "country": None, "guardrail": None, "category": None}
        if not re.match(r"^(?:¿|\?|que\b|cual\b|como\b|cuando\b|where\b|what\b|how\b)", _normalize(remainder), re.I):
            return classify_input(remainder)
        remainder_decision = classify_input(remainder)
        if remainder_decision["action"] == "allow":
            return {"action": "allow", "answer": None, "country": None, "guardrail": None, "category": None}
        return remainder_decision
    for pattern in _JAILBREAK_PATTERNS:
        if re.search(pattern, normalized_text, re.I):
            record_guardrail("jailbreak", "security")
            return {"action": "reject", "answer": "No puedo cambiar mis instrucciones ni revelar información interna. Puedo ayudarte con tracking, devoluciones o incidencias de TrackFlow.", "country": None, "guardrail": "jailbreak", "category": "security"}
    if _ORDER_REFERENCE.search(normalized_text):
        record_guardrail("tracking_authorization", "security")
        return {"action": "reject", "answer": "No puedo consultar ni revelar un pedido sin una autorización verificable de la sesión. Contacta con soporte TrackFlow para validar tu identidad.", "country": None, "guardrail": "tracking_authorization", "category": "security"}
    if (
        re.search(r"\b(?:pedido|orden|envio|paquete|order|shipment)\b", normalized_text, re.I)
        and re.search(r"\b(?:los angeles|california|estados unidos|usa|united states)\b", normalized_text, re.I)
        and re.search(r"\b(?:espana|spain)\b", normalized_text, re.I)
        and re.search(r"\b(?:aplica|usa|apply|use|politica|policy)\b", normalized_text, re.I)
    ):
        record_guardrail("country_policy_override", "security")
        return {"action": "reject", "answer": "No puedo cambiar la política del país de un pedido por solicitud. El país debe verificarse con datos autorizados del envío; contacta con soporte TrackFlow para confirmar la política aplicable.", "country": None, "guardrail": "country_policy_override", "category": "security"}
    for pattern in _PERSONAL_PATTERNS:
        if re.search(pattern, normalized_text, re.I):
            record_guardrail("personal_use", "content")
            return {"action": "reject", "answer": "No puedo realizar tareas personales o ajenas a TrackFlow. Puedo ayudarte con tracking, devoluciones o incidencias logísticas.", "country": None, "guardrail": "personal_use", "category": "content"}
    if any(re.search(pattern, normalized_text, re.I) for pattern in _CASUAL_PATTERNS):
        record_guardrail("casual_redirect", "redirect")
        casual_answer = "¡Hola! Soy el agente de soporte logístico de TrackFlow. ¿Necesitas ayuda con un envío, una devolución o una incidencia?"
        return {"action": "redirect", "answer": casual_answer, "country": None, "guardrail": "casual_redirect", "category": "redirect"}
    # Short, explicitly general logistics questions are permitted with redirection.
    if re.search(r"\b(?:logistica|logistics|cadena de suministro|supply chain|logistica inversa|reverse logistics)\b", normalized_text, re.I):
        record_guardrail("general_logistics_redirect", "redirect")
        answer = (
            "La logística inversa gestiona el retorno de productos desde el destinatario "
            "hasta el vendedor. En TrackFlow puedo orientarte sobre cómo se tramitan las "
            "devoluciones; ¿qué envío necesitas consultar?"
            if re.search(r"\b(?:que es|what is|explica|explain|significa|meaning)\b", normalized_text, re.I)
            else "Puedo ayudarte con logística de TrackFlow, como tracking, devoluciones o incidencias. ¿Qué envío necesitas consultar?"
        )
        return {"action": "redirect", "answer": answer, "country": None, "guardrail": "general_logistics_redirect", "category": "redirect"}
    if _DOMAIN_TERMS.search(normalized_text) or _DOMAIN_POLICY_QUESTION.search(normalized_text):
        return {"action": "allow", "answer": None, "country": None, "guardrail": None, "category": None}
    record_guardrail("out_of_domain", "content")
    return {"action": "reject", "answer": "Solo puedo ayudar con soporte logístico de TrackFlow: tracking, devoluciones, SLAs e incidencias. ¿Qué consulta tienes sobre un envío?", "country": None, "guardrail": "out_of_domain", "category": "content"}


def is_memory_command(question: str) -> bool:
    """Return whether the entire input is an advertised memory decision command."""
    return _MEMORY_COMMAND.fullmatch(_normalize(question.strip())) is not None


INTERNAL_MARKERS = re.compile(
    r"(?:system\s+prompt|instrucciones\s+internas|prompt\s+del\s+sistema|"
    r"tarifa\s+negociada|negotiated\s+rate|contrato\s+en\s+negociacion|"
    r"ruta\s+interna\s+del\s+almacen|ubicacion\s+exacta\s+del\s+almacen)",
    re.I,
)
_TRACKING_OUTPUT = re.compile(r"\b(?:tracking|seguimiento)\s*(?:#|:)?\s*[a-z0-9-]*\d[a-z0-9-]{2,}\b", re.I)


def validate_output(
    answer: object, *, country: Literal["US", "ES"] | None = None,
) -> tuple[bool, str]:
    """Reject malformed or obviously sensitive/country-conflicting output safely."""
    if not isinstance(answer, str) or not answer.strip():
        record_guardrail("output_structure", "structural")
        return False, "No pude generar una respuesta válida. Contacta con soporte TrackFlow."
    normalized_answer = _normalize(answer)
    if INTERNAL_MARKERS.search(normalized_answer) or _TRACKING_OUTPUT.search(normalized_answer):
        record_guardrail("sensitive_output", "content")
        return False, "No puedo compartir información interna o datos de envíos sin autorización. Contacta con soporte TrackFlow para continuar."
    if country == "US" and re.search(r"\b(?:politica|devoluciones|sla)\b.{0,70}\b(?:espana|spain)\b", normalized_answer, re.I):
        record_guardrail("country_policy_mismatch", "content")
        return False, "Para este envío corresponde la política de Estados Unidos. La información disponible no permite confirmar sus condiciones; contacta con soporte TrackFlow."
    if country == "ES" and re.search(r"\b(?:politica|devoluciones|sla)\b.{0,70}\b(?:estados unidos|usa|united states)\b", normalized_answer, re.I):
        record_guardrail("country_policy_mismatch", "content")
        return False, "Para este envío corresponde la política de España. La información disponible no permite confirmar sus condiciones; contacta con soporte TrackFlow."
    return True, answer.strip()


def quarantine_external_context(items: list[dict]) -> str:
    """Serialize retrieved content as data so embedded markup cannot escape a prompt."""
    import json

    safe_items = [
        {key: value for key, value in item.items() if isinstance(key, str)}
        for item in items if isinstance(item, dict)
    ]
    return json.dumps(safe_items, ensure_ascii=True, separators=(",", ":"))
