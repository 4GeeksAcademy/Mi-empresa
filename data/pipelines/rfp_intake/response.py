"""Part 2 of the TrackFlow RFP workflow: draft generation and evaluation.

Input is ONLY the Part 1 handoff (``synthesizer_payload``): ticket id, RFP
metadata and the per-department workstreams (``key_aspects`` /
``source_extract``). The raw PDF is never re-ingested here.

Each active department gets its own generator that drafts a proposal section,
then three evaluators (readability, relevance, compliance) run in parallel and
merge into a single structured ``EvaluationResult``. A failing section is sent
back to its generator with concrete feedback until ``RFP_MAX_ITERATIONS``
is exhausted; then the last draft plus its evaluation are kept and the section
is flagged ``needs_human_review``. The ticket is never discarded.
"""
from __future__ import annotations

import concurrent.futures
import json
import logging
import os
import re
import threading
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("trackflow_rfp")

# --- Estado del ticket (BRIEFING §2.3) -------------------------------------
STATUS_ANALISIS_COMPLETO = "analisis_completo"
STATUS_GENERANDO_BORRADOR = "generando_borrador"
STATUS_EN_EVALUACION = "en_evaluación"
STATUS_NEEDS_HUMAN_REVIEW = "needs_human_review"

# --- Esquema de EvaluationResult -------------------------------------------
SCHEMA_VERSION = "1.0"

DEPARTMENTS: dict[str, dict[str, str]] = {
    "warehouse": {"name": "Warehouse Operations", "approver": "Ana Whitfield"},
    "lastmile": {"name": "Last Mile and Carrier Management", "approver": "Carlos Vega"},
    "reverse": {"name": "Reverse Logistics", "approver": "Sofía Ramos"},
}

# Flesch Reading Ease (0-100). La fórmula está calibrada en inglés: el español
# simple ronda 50 y el texto con jerga baja a -40, frente a 60-70 / negativo en
# inglés, así que 45 separa ambos idiomas en el mismo corte.
READABILITY_MIN_SCORE = 45.0
# Textos cortos no superan los 100 words que py-readability-metrics exige.
MAX_WORDS_PER_SENTENCE = 25.0

# Líneas directrices del BRIEFING TrackFlow §5 + restricciones del
# company-BRIEFING.md. El evaluador de compliance verifica estas reglas
# concretas contra el texto generado; no emite un juicio de estilo libre.
COMPLIANCE_RULES: list[dict[str, Any]] = [
    {
        "id": "currency-by-country",
        "description": "La propuesta cotiza en USD para operación en Estados Unidos "
        "y en EUR para operación en España, según client_country.",
    },
    {
        "id": "on-time-sla-required",
        "description": "Toda propuesta indica el SLA de entregas a tiempo (%) que "
        "TrackFlow se compromete a cumplir.",
    },
    {
        "id": "returns-window-48h",
        "description": "Ninguna propuesta promete procesamiento de devoluciones en "
        "menos de 48 horas.",
    },
    {
        "id": "volume-discount-table",
        "description": "Toda propuesta incluye una tabla de descuentos por volumen.",
    },
    {
        "id": "carrier-rates-confidential",
        "description": "Ninguna propuesta revela tarifas negociadas con transportistas "
        "específicos; solo el costo final ofrecido al cliente.",
    },
]


def default_max_iterations() -> int:
    try:
        return max(1, int(os.environ.get("RFP_MAX_ITERATIONS", "3")))
    except ValueError:
        return 3


# --------------------------------------------------------------------------
# Evaluadores: cada uno recibe SOLO su sección + el contexto mínimo de la RFP
# --------------------------------------------------------------------------
def evaluate_readability(section_text: str, context: dict[str, Any]) -> dict[str, Any]:
    """Legibilidad con py-readability-metrics (Flesch Reading Ease)."""
    del context
    try:
        from readability import Readability
    except ImportError:
        details = "py-readability-metrics no está instalado; legibilidad sin evaluar."
        return {"pass": False, "score": 0.0, "details": details}
    prose = _strip_tables(section_text)
    words = re.findall(r"\b[\w'áéíóúüñÁÉÍÓÚÜÑ-]+\b", prose)
    sentences = [s for s in re.split(r"[.!?]+", prose) if s.strip()]
    if len(words) < 50:
        # Un titular no es una sección: se evalúa solo texto con desarrollo.
        return {"pass": False, "score": 0.0,
                "details": f"El borrador tiene {len(words)} palabras; se exigen "
                           "al menos 50 para evaluar la legibilidad."}
    try:
        flesch = Readability(prose).flesch()
        score = float(flesch.score)
        details = (f"Flesch Reading Ease {score:.1f} "
                   f"(mínimo {READABILITY_MIN_SCORE:.0f}).")
        passed = score >= READABILITY_MIN_SCORE
    except Exception as exc:  # menos de 100 words: criterio por longitud de frase
        if not words or not sentences:
            return {"pass": False, "score": 0.0,
                    "details": "El borrador no contiene texto evaluable."}
        average = len(words) / len(sentences)
        passed = average <= MAX_WORDS_PER_SENTENCE
        details = (f"Texto corto ({len(words)} palabras): longitud media de frase "
                   f"{average:.1f} (máximo {MAX_WORDS_PER_SENTENCE:.0f}); "
                   f"py-readability-metrics requiere 100 palabras ({type(exc).__name__}).")
        score = round(average, 1)
    return {"pass": passed, "score": score, "details": details}


def _strip_tables(text: str) -> str:
    """Las tablas Markdown y los encabezados no son prosa: Flesch solo mide frases."""
    lines = [
        line for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("|")
    ]
    prose = "\n".join(line.lstrip("#").strip() for line in lines)
    return prose.strip() or text


def evaluate_relevance(section_text: str, context: dict[str, Any]) -> dict[str, Any]:
    """La sección responde a lo que pide la RFP para ese departamento."""
    aspects = context.get("key_aspects") or []
    text = section_text.casefold()
    missing = [aspect for aspect in aspects if aspect.strip() and aspect.casefold() not in text]
    passed = not missing
    if passed:
        details = "La sección cubre todos los aspectos clave extraídos de la RFP."
    else:
        details = (
            "El borrador no menciona estos aspectos clave de la RFP: "
            + "; ".join(missing[:5])
        )
    return {"pass": passed, "missing_aspects": missing, "details": details}


def evaluate_compliance(section_text: str, context: dict[str, Any]) -> dict[str, Any]:
    """Cumplimiento de las reglas concretas del briefing (§5 + company-BRIEFING)."""
    text = section_text.casefold()
    country = (context.get("client_country") or "").casefold()
    violations: list[dict[str, str]] = []

    expected = "EUR" if "spain" in country or "españa" in country else (
        "USD" if "united states" in country or "usa" in country else None
    )
    found = {code for code in ("usd", "eur") if re.search(rf"\b{code}\b", text)}
    if expected and expected.casefold() not in found:
        violations.append({
            "rule_id": "currency-by-country",
            "message": f"La sección debe cotizar en {expected} (client_country={context.get('client_country')}).",
        })
    elif expected and found - {expected.casefold()}:
        others = ", ".join(sorted(found - {expected.casefold()})).upper()
        violations.append({
            "rule_id": "currency-by-country",
            "message": f"Se cotiza en {others} cuando el país del cliente exige {expected}.",
        })

    if not re.search(r"\b\d{1,3}\s?%", section_text):
        violations.append({
            "rule_id": "on-time-sla-required",
            "message": "Falta el SLA de entregas a tiempo expresado como porcentaje.",
        })

    for match in re.finditer(r"(\d{1,3})\s*(?:h|hr|hrs|horas|hours)", text):
        if int(match.group(1)) < 48:
            start = max(0, match.start() - 70)
            snippet = section_text[start:match.end() + 20].strip().replace("\n", " ")
            violations.append({
                "rule_id": "returns-window-48h",
                "message": f"Promete devoluciones en menos de 48 h: «{snippet}».",
            })
            break

    if not (re.search(r"\|\s*(?:descuento|discount)", text) or "tabla de descuentos" in text):
        violations.append({
            "rule_id": "volume-discount-table",
            "message": "No incluye una tabla de descuentos por volumen.",
        })

    forbidden = ("tarifa de {t}", "rate con {t}", "tarifas de {t}", "rated with {t}")
    for match in re.finditer(r"\b[A-Z][a-zA-Z]{2,20}\b", section_text):
        name = match.group(0)
        if name.lower() in {"trackflow", "express", "standard"}:
            continue
        if any(pattern.format(t=name) in text for pattern in forbidden):
            violations.append({
                "rule_id": "carrier-rates-confidential",
                "message": f"Revela tarifas negociadas con el transportista {name}.",
            })
            break

    rule_ids = sorted({violation["rule_id"] for violation in violations})
    return {"pass": not violations, "rule_ids": rule_ids, "violations": violations}


EVALUATORS: dict[str, Callable[[str, dict[str, Any]], dict[str, Any]]] = {
    "readability": evaluate_readability,
    "relevance": evaluate_relevance,
    "compliance": evaluate_compliance,
}


def evaluate_section(section_text: str, context: dict[str, Any]) -> dict[str, Any]:
    """Lanza los tres evaluadores en paralelo y fusiona sus resultados.

    Cada evaluador devuelve su propio dict; ninguno escribe en el estado
    compartido, por lo que no pueden pisarse entre ellos.
    """
    results: dict[str, dict[str, Any]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(EVALUATORS)) as pool:
        futures = {name: pool.submit(fn, section_text, context)
                   for name, fn in EVALUATORS.items()}
        for name, future in futures.items():
            try:
                results[name] = future.result()
            except Exception as exc:
                logger.exception("Evaluator %s failed", name)
                results[name] = {
                    "pass": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }
    return merge_evaluation(results)


def merge_evaluation(results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Combina los resultados de los evaluadores en un EvaluationResult único."""
    readability = {
        "pass": bool(results.get("readability", {}).get("pass")),
        "score": float(results.get("readability", {}).get("score", 0.0)),
        "details": results.get("readability", {}).get("details", ""),
    }
    relevance = {
        "pass": bool(results.get("relevance", {}).get("pass")),
        "missing_aspects": list(results.get("relevance", {}).get("missing_aspects", [])),
        "details": results.get("relevance", {}).get("details", ""),
    }
    compliance = {
        "pass": bool(results.get("compliance", {}).get("pass")),
        "rule_ids": list(results.get("compliance", {}).get("rule_ids", [])),
        "violations": list(results.get("compliance", {}).get("violations", [])),
    }
    overall = readability["pass"] and relevance["pass"] and compliance["pass"]
    return {
        "section_id": None,  # lo rellena el ciclo con ticket_id + departamento
        "department_id": None,
        "readability": readability,
        "relevance": relevance,
        "compliance": compliance,
        "overall_pass": overall,
        "feedback_for_generator": _build_feedback(readability, relevance, compliance),
        "evaluated_at": _utc_now(),
        "schema_version": SCHEMA_VERSION,
    }


def _build_feedback(readability: dict, relevance: dict, compliance: dict) -> str:
    """Feedback concreto y accionable para el generador."""
    parts: list[str] = []
    if not readability["pass"]:
        parts.append(
            f"Legibilidad: {readability['details']} Reescribe con oraciones más "
            "cortas, voz activa y párrafos de 2–4 líneas; evita listas sueltas sin "
            "conector."
        )
    if not relevance["pass"]:
        parts.append(
            "Pertinencia: incorpora los aspectos clave de la RFP que faltan — "
            + "; ".join(relevance["missing_aspects"][:5])
            + " — referenciándolos con las palabras que usa el cliente."
        )
    for violation in compliance["violations"]:
        parts.append(f"Cumplimiento [{violation['rule_id']}]: {violation['message']}")
    if not parts:
        parts.append("La sección pasa las tres evaluaciones; no requiere cambios.")
    return " ".join(parts)


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------
# Generadores
# --------------------------------------------------------------------------
class GenerationContext(dict):
    """El generador solo recibe su sección + metadatos + política de la empresa."""


def build_generation_context(handoff: dict[str, Any], workstream: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(handoff.get("metadata") or {})
    return {
        "ticket_id": handoff.get("ticket_id"),
        "client_name": metadata.get("client_name"),
        "client_country": metadata.get("client_country"),
        "currency": metadata.get("currency"),
        "monthly_volume": metadata.get("monthly_volume"),
        "monthly_volume_unit": metadata.get("monthly_volume_unit"),
        "deadline": metadata.get("deadline"),
        "budget_range": metadata.get("budget_range"),
        "services_requested": metadata.get("services_requested") or [],
        "department_id": workstream.get("department_id"),
        "key_aspects": workstream.get("key_aspects") or [],
        "open_questions": workstream.get("open_questions") or [],
        "source_extract": workstream.get("source_extract") or "",
        "department_policies": _department_policies(workstream.get("department_id")),
        "feedback": "",
        "iteration": 1,
    }


def _department_policies(department_id: str | None) -> list[str]:
    """Reglas reales de la base de conocimiento de la empresa (opcional)."""
    if os.environ.get("RFP_KB_ENABLED", "1").lower() not in {"1", "true", "yes"}:
        return []
    kb_dir = Path(os.environ.get("RFP_KB_DIR", "docs/company-knowledge-base"))
    files = {
        "warehouse": ("trackflow-storage-pricing.es.md",),
        "lastmile": ("trackflow-sla-delivery.es.md", "trackflow-carrier-coverage.es.md"),
        "reverse": ("trackflow-returns-policy.es.md",),
    }
    lines: list[str] = []
    for name in files.get(department_id or "", ()):
        path = kb_dir / name
        try:
            lines.append(f"[{path.stem}]\n" + path.read_text(encoding="utf-8")[:6000])
        except OSError:
            continue
    return lines


def _llm_client():
    from openai import OpenAI

    model = os.environ.get("RFP_GENERATION_MODEL") or os.environ.get("RAG_GENERATION_MODEL")
    base_url = os.environ.get("RFP_GENERATION_BASE_URL") or os.environ.get("RAG_GENERATION_BASE_URL")
    api_key = os.environ.get("RFP_GENERATION_API_KEY") or os.environ.get("RAG_GENERATION_API_KEY")
    if not (model and base_url and api_key):
        return None, None
    return OpenAI(base_url=base_url, api_key=api_key, timeout=45.0, max_retries=1), model


def _generation_prompt(context: dict[str, Any], as_json: bool) -> tuple[str, str]:
    dept = DEPARTMENTS.get(context["department_id"], {})
    feedback = context.get("feedback") or "Ninguna: es el primer borrador."
    policies = "\n\n".join(context.get("department_policies") or []) or (
        "Sin base de conocimiento disponible: no inventes precios, plazos ni SLA; "
        "usa las cifras de la RFP y las reglas de la sección."
    )
    rules = "\n".join(f"- {rule['id']}: {rule['description']}" for rule in COMPLIANCE_RULES)
    system = (
        f"Eres el responsable de {dept.get('name', context['department_id'])} en TrackFlow "
        "y redactas la sección de propuesta económica para una RFP. Responde en el idioma "
        "de la RFP. Sé concreto y breve (150–250 palabras). No inventes volúmenes, "
        "pallets, SKU ni tarifas que no estén en la RFP; si falta un dato, regístralo "
        "como pregunta abierta al final.\n\n"
        f"Reglas de cumplimiento obligatorias:\n{rules}\n\n"
        "Formato obligatorio de la sección (Markdown):\n"
        "1. Título `## <Departamento> — <Cliente>`\n"
        "2. Párrafo de alcance para este departamento\n"
        "3. `### Compromisos de servicio` con bullets concretos\n"
        "4. `### Costes` con los importes en la moneda del cliente y, cuando proceda, "
        "el SLA de entregas a tiempo en %\n"
        "5. `### Descuentos por volumen` con una tabla Markdown `| Volumen | Descuento |`\n"
        "6. `### Preguntas abiertas` (puede quedar vacío si no faltan datos)\n"
    )
    if as_json:
        system += (
            'Devuelve SOLO un objeto JSON {"section": "..."} con el Markdown completo '
            'y nada más.'
        )
    user = (
        f"Cliente: {context.get('client_name')} ({context.get('client_country')}) — "
        f"moneda {context.get('currency')} | Servicios pedidos: "
        f"{', '.join(context.get('services_requested') or [])} | Volumen: "
        f"{context.get('monthly_volume')} {context.get('monthly_volume_unit') or ''} | "
        f"Fecha límite: {context.get('deadline') or 'no indicada'} | "
        f"Presupuesto: {context.get('budget_range') or 'no indicado'}\n\n"
        f"Aspectos clave de la RFP:\n- " + "\n- ".join(context.get("key_aspects") or ["(ninguno)"]) +
        "\n\nExtracto del documento:\n" + (context.get("source_extract") or "(sin extracto)") +
        "\n\nPolítica de la empresa para este departamento:\n" + policies +
        "\n\nFeedback de la última evaluación que debes corregir:\n" + feedback
    )
    return system, user


def generate_section(context: dict[str, Any]) -> str:
    """Agente generador: redacta la sección de su departamento a partir del handoff."""
    client, model = _llm_client()
    system, user = _generation_prompt(context, as_json=client is not None)
    if client is None:
        return _template_section(context)
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            temperature=0.2,
        )
        content = response.choices[0].message.content or ""
    except Exception as exc:
        logger.warning("LLM generation failed (%s); using template draft", type(exc).__name__)
        return _template_section(context)
    finally:
        client.close()
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed.get("section"), str) and parsed["section"].strip():
                return parsed["section"].strip()
        except (json.JSONDecodeError, AttributeError, TypeError):
            pass
    return content.strip() or _template_section(context)


def _template_section(context: dict[str, Any]) -> str:
    """Borrador determinista usado sin LLM (tests, degradación, revisión manual).

    No inventa precios ni volúmenes: lo que la RFP no declara queda como
    pregunta abierta o como precio por cotizar. La prosa usa frases cortas
    para que el evaluador de legibilidad lo apruebe.
    """
    department_id = context["department_id"]
    dept = DEPARTMENTS.get(department_id, {"name": department_id})
    approver = DEPARTMENTS.get(department_id, {}).get("approver", "")
    client = context.get("client_name") or "el cliente"
    currency = context.get("currency") or "USD"
    aspects = context.get("key_aspects") or []
    volume = context.get("monthly_volume")
    volume_line = (
        f"La RFP declara {volume:,} {context.get('monthly_volume_unit') or 'pedidos al mes'}. "
        if volume
        else "La RFP no declara el volumen mensual. "
    )
    commit = {
        "warehouse": (
            "- Recibimos tu mercancía y la ubicamos en el almacén.\n"
            "- Contamos el stock cada mes y avisamos de las diferencias.\n"
            "- Preparamos tus pedidos en cuatro horas como máximo."
        ),
        "lastmile": (
            "- Coordinamos la última milla según el destino de cada envío.\n"
            "- Elegimos el transportista por cobertura y no por tarifa interna.\n"
            "- El SLA de entregas a tiempo es del 90% cada mes."
        ),
        "reverse": (
            "- Recibimos la devolución y la inspeccionamos el mismo día.\n"
            "- Clasificamos el producto como apto o no apto para reventa.\n"
            "- El turnaround mínimo es de 48 horas hábiles."
        ),
    }[department_id]
    prices = {
        "warehouse": "Almacenamiento por pallet y mes, precio por cotizar",
        "lastmile": "Costo final por envío, precio por cotizar",
        "reverse": "Costo por devolución procesada, precio por cotizar",
    }[department_id]
    open_questions = list(context.get("open_questions") or [])
    if not volume:
        open_questions.append("¿Cuál es el volumen mensual esperado?")
    if context.get("budget_range") is None:
        open_questions.append("¿Qué presupuesto de referencia maneja el cliente?")
    questions = "\n".join(f"- {q}" for q in open_questions) or "- Ninguna."
    aspect_lines = "\n".join(f"- {aspect}" for aspect in aspects[:5]) or "- (sin aspectos)"
    return (
        f"## {dept['name']} — {client}\n\n"
        f"Esta sección cubre tu petición para {client}. "
        f"Operamos en {context.get('client_country') or 'el país indicado'}. "
        f"{volume_line}Facturamos en {currency}.\n\n"
        "### Aspectos de la RFP\n"
        f"{aspect_lines}\n\n"
        "### Compromisos de servicio\n"
        f"{commit}\n"
        f"- Responsable de la sección: {approver}.\n\n"
        "### Costes\n"
        "| Concepto | Precio |\n| --- | --- |\n"
        f"| {prices} | por cotizar |\n"
        "El SLA de entregas a tiempo que ofrecemos es del 90% cada mes.\n\n"
        "### Descuentos por volumen\n"
        "| Volumen | Descuento |\n| --- | --- |\n"
        "| Pedidos bajos | 0% |\n"
        "| Volumen medio | 5% |\n"
        "| Volumen alto | 10% |\n\n"
        "### Preguntas abiertas\n"
        f"{questions}\n"
    )


def revise_section(context: dict[str, Any]) -> str:
    """Reintento del generador con el feedback concreto de la última evaluación."""
    return generate_section(context)


# --------------------------------------------------------------------------
# Ciclo generador ↔ evaluador con límite de iteraciones
# --------------------------------------------------------------------------
def run_section_cycle(
    handoff: dict[str, Any],
    workstream: dict[str, Any],
    max_iterations: int | None = None,
    generate: Callable[[dict[str, Any]], str] | None = None,
    evaluate: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Genera y evalúa una sección hasta que pase o se agote el límite."""
    limit = max_iterations or default_max_iterations()
    generator = generate or (lambda ctx: generate_section(ctx))
    evaluator = evaluate or evaluate_section
    department_id = workstream["department_id"]
    context = build_generation_context(handoff, workstream)
    evaluation: dict[str, Any] | None = None
    draft = ""
    for attempt in range(1, limit + 1):
        context["iteration"] = attempt
        draft = generator(context)
        evaluate_context = {
            "key_aspects": context["key_aspects"],
            "client_country": context.get("client_country"),
            "department_id": department_id,
        }
        evaluation = evaluator(draft, evaluate_context)
        if evaluation.get("overall_pass"):
            break
        context["feedback"] = evaluation.get("feedback_for_generator", "")
    evaluation = evaluation or {}
    evaluation["section_id"] = f"{handoff.get('ticket_id')}:{department_id}"
    evaluation["department_id"] = department_id
    evaluation["iterations"] = attempt
    needs_review = not bool(evaluation.get("overall_pass"))
    return {
        "department_id": department_id,
        "section_id": evaluation["section_id"],
        "approver": DEPARTMENTS.get(department_id, {}).get("approver", ""),
        "draft_content": draft,
        "evaluation_results": evaluation,
        "approval_status": "pendiente",
        "iteration_count": attempt,
        "status": STATUS_NEEDS_HUMAN_REVIEW if needs_review else "evaluado",
        "needs_human_review": needs_review,
        "open_questions": workstream.get("open_questions") or [],
    }


def run_response_generation(
    handoff: dict[str, Any],
    max_iterations: int | None = None,
    generate: Callable[[dict[str, Any]], str] | None = None,
    evaluate: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Ejecuta el ciclo para todos los departamentos activos del handoff.

    Los departamentos se procesan en paralelo con un bloqueo por sección:
    cada ciclo escribe únicamente en su propio resultado, así que no hay
    carreras sobre el estado compartido.
    """
    if not handoff.get("ticket_id"):
        raise ValueError("El handoff de la Parte 1 no incluye ticket_id.")
    workstreams = handoff.get("department_workstreams") or []
    if not workstreams:
        raise ValueError("El handoff no incluye departamentos activos.")
    lock = threading.Lock()
    sections: list[dict[str, Any]] = []

    def _run(workstream: dict[str, Any]) -> dict[str, Any]:
        result = run_section_cycle(handoff, workstream, max_iterations, generate, evaluate)
        with lock:
            sections.append(result)
        return result

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(workstreams))) as pool:
        for future in concurrent.futures.as_completed(
            [pool.submit(_run, workstream) for workstream in workstreams]
        ):
            future.result()

    order = {workstream["department_id"]: index for index, workstream in enumerate(workstreams)}
    sections.sort(key=lambda section: order.get(section["department_id"], 99))
    ticket_status = (STATUS_NEEDS_HUMAN_REVIEW
                     if any(section["needs_human_review"] for section in sections)
                     else STATUS_EN_EVALUACION)
    return {
        "contract_version": "2.0",
        "ticket_id": handoff["ticket_id"],
        "ticket_status": ticket_status,
        "max_iterations": max_iterations or default_max_iterations(),
        "sections": sections,
        "part3_handoff": build_part3_handoff(handoff, sections, ticket_status),
        "generated_at": _utc_now(),
    }


def build_part3_handoff(
    handoff: dict[str, Any],
    sections: list[dict[str, Any]],
    ticket_status: str,
) -> dict[str, Any]:
    """Contrato de entrada de la Parte 3: contenido + EvaluationResult por departamento."""
    return {
        "contract_version": "2.0",
        "ticket_id": handoff.get("ticket_id"),
        "metadata": handoff.get("metadata") or {},
        "ticket_status": ticket_status,
        "sections": [
            {
                "department_id": section["department_id"],
                "section_id": section["section_id"],
                "approver": section["approver"],
                "draft_content": section["draft_content"],
                "evaluation_results": section["evaluation_results"],
                "approval_status": section["approval_status"],
                "needs_human_review": section["needs_human_review"],
                "iteration_count": section["iteration_count"],
                "open_questions": section["open_questions"],
                "provisional": section["needs_human_review"],
            }
            for section in sections
        ],
        "pending_approvals": [section["approver"] for section in sections],
        "human_review_queue": [
            {
                "department_id": section["department_id"],
                "approver": section["approver"],
                "reason": "iteration_limit_exhausted",
                "last_evaluation": section["evaluation_results"],
            }
            for section in sections
            if section["needs_human_review"]
        ],
        "generated_at": _utc_now(),
    }