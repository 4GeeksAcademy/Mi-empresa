"""Part 3 of the TrackFlow RFP workflow: human approval and document closure.

Construye sobre el contrato ``part3_handoff`` v2.0 de la Parte 2 (response.py).
Cada departamento activo tiene SU PROPIO grafo de aprobación con thread_id
namespaced ``rfp-{ticket_id}:{department}``; el coordinador del ticket usa
``rfp-{ticket_id}``. Los hilos se arrancan en paralelo y cada uno se pausa con
``interrupt`` SOLO en su propia rama: aprobar un departamento no bloquea ni
despierta a los demás (prueba: tests/pipelines/test_rfp_approval.py).

Checkpointer: SqliteSaver persistente (nada en memoria) — ver
``open_approval_env``. El checkpoint del interrupt se escribe ANTES de la
pausa: langgraph persiste el checkpoint de la superstep que contiene el
``interrupt`` antes de devolver el control.

Flujo::

    start_approvals ──► hilos por departamento en paralelo
                          └─ review (guardrails + interrupt)
                                 │ decisión humana validada (aprobar/rechazar/request_changes)
                                 ▼
              rework pendiente → vuelve al generador Parte 2 (mismo ticket)
                                 ▼
              coordinador (detect → arbitrate → check → finalize|wait)
                                 │ todos firman y sin conflictos
                                 ▼
                    FinalDocument (ticket_id, sections, currency, generated_at)

Decisiones de diseño documentadas:

1. ``rechazar`` / ``request_changes`` vuelven al generador de la Parte 2
   DENTRO del mismo ticket y thread: ``review`` consume ``rework_pending``
   llamando a la pareja inyectable ``generate``/``evaluate`` (los mismos de la
   Parte 2) y vuelve a ``interrupt``. Nunca se reinicia la ejecución.
2. Límite de iteraciones: ``rework_runs`` cuenta los re-trabajos de la
   sección; al llegar a ``RFP_MAX_ITERATIONS`` NO se llama más al generador
   (guardrail), pero la decisión humana sigue disponible. Para
   ``currency-mismatch`` el arbitraje lo convierte en rechazo terminal (§7:
   "rechazar si no se resuelve tras el límite de iteraciones").
3. Árbitro fijo por trigger (§7) — nunca un LLM: la detección es sobre estado
   estructurado (campos tipados del handoff y evaluaciones) y la resolución es
   determinista (``ARBITER_ACTIONS``) o del responsable nombrado
   (``RFP_ARBITER_MODE=human``).
4. Coordenadas de ``returns-sla-breach``: la regla "Sofía Ramos rechaza su
   sección" es un guardrail automático (la rama ``reverse`` fuerza
   ``request_changes`` mientras su evaluación embeba devoluciones <48 h, §5);
   Miguel Torres (nodo de arbitraje) interviene cuando OTRA sección aún
   embebe esa promesa.
"""
from __future__ import annotations

import logging
import operator
import os
import re
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Callable, Iterator, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command, interrupt
from langchain_core.runnables import RunnableConfig

from .response import (
    DEPARTMENTS,
    _utc_now,
    build_generation_context,
    default_max_iterations,
    evaluate_section,
    generate_section,
)

logger = logging.getLogger("trackflow_rfp")

# --- Estado del ticket (BRIEFING §2.3) -------------------------------------
STATUS_ESPERANDO_APROBACION = "esperando_aprobación"
STATUS_TERMINADO = "terminado"

# --- Decisiones humanas (punto de entrada explícito de resume) -------------
DECISION_APROBAR = "aprobar"
DECISION_RECHAZAR = "rechazar"
DECISION_CAMBIOS = "request_changes"
VALID_DECISIONS = (DECISION_APROBAR, DECISION_RECHAZAR, DECISION_CAMBIOS)

# --- Triggers de conflicto y árbitro fijo (BRIEFING §7) --------------------
TRIGGER_VOLUME_VS_CAPACITY = "volume-vs-capacity"
TRIGGER_RETURNS_SLA_BREACH = "returns-sla-breach"
TRIGGER_CURRENCY_MISMATCH = "currency-mismatch"

#: Árbitro fijo por trigger (humano nombrado; nunca un LLM votando).
ARBITERS: dict[str, str] = {
    TRIGGER_VOLUME_VS_CAPACITY: "Miguel Torres",
    TRIGGER_RETURNS_SLA_BREACH: "Miguel Torres",
    TRIGGER_CURRENCY_MISMATCH: "Miguel Torres",
}

#: Acción determinista del árbitro por trigger (§7, "Regla de resolución").
ARBITER_ACTIONS: dict[str, str] = {
    TRIGGER_VOLUME_VS_CAPACITY: "cap_volume",
    TRIGGER_RETURNS_SLA_BREACH: "forbid_returns_under_48h",
    TRIGGER_CURRENCY_MISMATCH: "rewrite_currency",
}

DEPT_ORDER = ("warehouse", "lastmile", "reverse")

#: Violación §5 que dispara el guardrail de devoluciones.
RETURNS_RULE = "returns-window-48h"


class DecisionValidationError(ValueError):
    """La respuesta humana no cumple el contrato de decisión."""


class ApprovalError(RuntimeError):
    """Operación de aprobación inválida (thread inexistente, etc.)."""


# --------------------------------------------------------------------------
# Identidad del checkpointer (Punto C: thread_id namespaced por ticket)
# --------------------------------------------------------------------------
def thread_id(ticket_id: str) -> str:
    """thread_id del coordinador del ticket: ``rfp-{ticket_id}``."""
    return f"rfp-{ticket_id}"


def department_thread_id(ticket_id: str, department_id: str) -> str:
    """thread_id de la rama de un departamento: ``rfp-{ticket_id}:{department}``."""
    return f"rfp-{ticket_id}:{department_id}"


def default_checkpoint_db() -> Path:
    """Base SQLite del checkpointer — persistente, compartida entre workers."""
    return Path(os.environ.get(
        "RFP_APPROVAL_DB",
        os.path.join(os.environ.get("RFP_CHECKPOINT_DIR", "data/checkpoints"),
                     "rfp_approval.db"),
    ))


# --------------------------------------------------------------------------
# Validación de la respuesta humana (antes de reinsertarla en el grafo)
# --------------------------------------------------------------------------
def validate_decision(payload: Any, department_id: str) -> dict[str, Any]:
    """Valida la decisión humana ANTES de reinsertarla vía ``Command(resume=...)``.

    Requisitos: decisión conocida (aprobar/rechazar/request_changes), el
    aprobador exacto del departamento (BRIEFING §2.1, sin escalera
    jerárquica) y comentario obligatorio para rechazo/cambios.
    """
    if not isinstance(payload, dict):
        raise DecisionValidationError(
            "La decisión debe ser un objeto con decision, approver y comment.")
    decision = payload.get("decision")
    if decision not in VALID_DECISIONS:
        raise DecisionValidationError(
            "decision inválida: {!r}; use uno de {}.".format(
                decision, ", ".join(VALID_DECISIONS)))
    expected_approver = DEPARTMENTS.get(department_id, {}).get("approver")
    if not expected_approver:
        raise DecisionValidationError(
            f"Departamento desconocido: {department_id!r}.")
    approver = payload.get("approver")
    if approver != expected_approver:
        raise DecisionValidationError(
            f"approver inválido para {department_id}: "
            f"se espera {expected_approver!r}.")
    comment = payload.get("comment") or ""
    if decision in (DECISION_RECHAZAR, DECISION_CAMBIOS) and not str(comment).strip():
        raise DecisionValidationError(
            f"{decision} requiere un comment con la razón del rechazo/cambio.")
    return {
        "decision": decision,
        "approver": approver,
        "comment": str(comment).strip(),
        "decided_at": _utc_now(),
    }


# --------------------------------------------------------------------------
# Detección de conflictos en ESTADO ESTRUCTURADO (no texto libre)
# --------------------------------------------------------------------------
def expected_currency(client_country: str | None) -> str | None:
    """Moneda por ``client_country`` (§5): EE. UU. → USD, España → EUR."""
    country = (client_country or "").casefold()
    if "spain" in country or "españa" in country:
        return "EUR"
    if "united states" in country or "usa" in country or country == "us":
        return "USD"
    return None


def _violation_flags(section: dict[str, Any]) -> list[str]:
    compliance = (section.get("evaluation_results") or {}).get("compliance") or {}
    return sorted({v.get("rule_id", "") for v in compliance.get("violations") or []})


def detect_conflicts(handoff: dict[str, Any],
                     sections: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Devuelve los conflictos §7 como estado estructurado (campos tipados).

    Los agentes solo señalan: aquí NO se decide la resolución, solo se emiten
    ``trigger`` + ``departments`` para el nodo de arbitraje.
    """
    sections = sections if sections is not None else (handoff.get("sections") or [])
    metadata = handoff.get("metadata") or {}
    expected = expected_currency(metadata.get("client_country"))
    conflicts: list[dict[str, Any]] = []

    # currency-mismatch: moneda ≠ mapeo del país, o dos secciones cotizando
    # en monedas distintas.
    found: dict[str, set[str]] = {}
    mismatched: set[str] = set()
    for section in sections:
        text = section.get("draft_content") or ""
        codes = {c for c in ("USD", "EUR") if re.search(rf"\b{c}\b", text)}
        if not codes:
            continue
        found[section["department_id"]] = codes
        if expected and codes != {expected}:
            mismatched.add(section["department_id"])
    currencies = set().union(*found.values()) if found else set()
    if mismatched or len(currencies) > 1:
        conflicts.append({
            "trigger": TRIGGER_CURRENCY_MISMATCH,
            "departments": sorted(mismatched or set(found)),
            "detail": {"expected": expected, "found": sorted(currencies)},
        })

    # returns-sla-breach: violación §5 ya detectada en la evaluación tipada
    # (o señal explícita ``return_sla_breach``).
    offenders = sorted({
        s["department_id"] for s in sections
        if RETURNS_RULE in _violation_flags(s)
        or s.get("return_sla_breach") is True
    })
    if offenders:
        # Si la sección ofensora es 'reverse', su guardrail automático ya
        # fuerza request_changes (§7); el arbitraje interviene cuando OTRO
        # departamento aún embebe esa promesa.
        departments = [d for d in offenders if d != "reverse"] or offenders
        conflicts.append({
            "trigger": TRIGGER_RETURNS_SLA_BREACH,
            "departments": sorted(set(departments)),
            "detail": {"offenders": offenders},
        })

    # volume-vs-capacity: el volumen mensual asumido por lastmile no lo
    # soporta la capacidad comprometida de warehouse — campos tipados
    # (señales del evaluador + volumen declarado en la RFP).
    volume = metadata.get("monthly_volume")
    warehouse = next((s for s in sections if s["department_id"] == "warehouse"), None)
    lastmile = next((s for s in sections if s["department_id"] == "lastmile"), None)
    if warehouse is not None and lastmile is not None and volume is not None:
        capacity_short = bool(warehouse.get("capacity_shortfall")) or any(
            "capac" in str(q).casefold() or "volumen" in str(q).casefold()
            for q in (warehouse.get("open_questions") or []))
        volume_assumed = bool(lastmile.get("volume_assumption")) or bool(
            re.search(r"volumen mensual|declar[ao] \d", lastmile.get("draft_content") or "",
                      re.IGNORECASE))
        if capacity_short and volume_assumed:
            conflicts.append({
                "trigger": TRIGGER_VOLUME_VS_CAPACITY,
                "departments": ["lastmile", "warehouse"],
                "detail": {"monthly_volume": volume},
            })
    return conflicts


# --------------------------------------------------------------------------
# Guardrails automáticos: rewrites deterministas que el árbitro exige
# --------------------------------------------------------------------------
def apply_arbiter_rules(draft: str, instruction: dict[str, Any],
                        metadata: dict[str, Any]) -> str:
    """Resuelve la regla §7 sobre el borrador; devuelve el texto reescrito."""
    action = instruction.get("action")
    if action == "rewrite_currency":
        expected = (expected_currency(metadata.get("client_country"))
                    or metadata.get("currency"))
        if expected in ("EUR", "USD"):
            draft = re.sub(r"\b(EUR|USD)\b", expected, draft)
    elif action == "cap_volume":
        # §7: limitar el volumen de la propuesta a la capacidad de warehouse.
        draft = re.sub(
            r"La RFP declara [^.]*\.",
            "El volumen de la propuesta queda limitado a la capacidad de "
            "warehouse confirmada en onboarding.",
            draft, count=1)
    elif action == "forbid_returns_under_48h":
        def _floor(match: re.Match) -> str:
            hours = int(match.group(1))
            return "48 horas" if hours < 48 else match.group(0)
        draft = re.sub(r"\b(\d{1,3})\s*(?:h|hr|hrs|horas|hours)\b",
                       _floor, draft, flags=re.IGNORECASE)
    return draft


# --------------------------------------------------------------------------
# Trazabilidad por ejecución de nodo (agente, input, output, timestamp)
# --------------------------------------------------------------------------
def make_node_trace(node: str, department: str | None,
                    inputs: Any, outputs: Any) -> dict[str, Any]:
    return {
        "node": node,
        "agent": node,
        "department": department,
        "input": inputs,
        "output": outputs,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# --------------------------------------------------------------------------
# Estado de los grafos
# --------------------------------------------------------------------------
class DepartmentApprovalState(TypedDict, total=False):
    """Estado de la rama de aprobación de UN departamento."""
    ticket_id: str
    department: str
    approver: str
    workstream: dict[str, Any]
    metadata: dict[str, Any]
    section_id: str
    draft: str
    evaluation: dict[str, Any]
    iteration_count: int
    approval_status: str          # pendiente|aprobado|rechazado|cambios_solicitados
    decision: dict[str, Any]
    rework_pending: bool          # consumido por el siguiente ciclo (Parte 2)
    rework_runs: int              # iteraciones del ciclo restante (guardrail)
    rework_instructions: dict[str, Any]  # trigger/arbiter/action del arbitraje
    arbitration_blocked: bool     # arbitraje agotó el límite (§7)
    iteration_limit_reached: bool
    round: int                    # rondas de interrupt en esta ejecución
    max_iterations: int           # límite de ciclos del ciclo restante (guardrail)


class CoordinatorState(TypedDict, total=False):
    """Estado del coordinador del ticket (thread rfp-{ticket_id})."""
    ticket_id: str
    active_departments: list[str]
    sections: Annotated[dict[str, dict[str, Any]], operator.or_]
    sections_metadata: dict[str, Any]
    conflicts: list[dict[str, Any]]
    decision: str                 # arbitrate | continue | wait | finalize
    arbitration_rounds: int
    arbitration_exhausted: dict[str, Any]
    final_document: dict[str, Any]


# --------------------------------------------------------------------------
# Nodo de aprobación por departamento (Punto A)
# --------------------------------------------------------------------------
def _run_rework_cycle(state: DepartmentApprovalState,
                      generate: Callable[[dict[str, Any]], str],
                      evaluate: Callable[[str, dict[str, Any]], dict[str, Any]],
                      instruction: dict[str, Any] | None) -> dict[str, Any]:
    """Vuelve al generador/evaluador de la Parte 2 dentro del MISMO ticket.

    Reutiliza la pareja inyectable de la Parte 2 (``generate_section`` /
    ``evaluate_section`` por defecto) con el feedback de la decisión humana y
    aplica los rewrites deterministas del arbitraje si están pendientes.
    """
    department = state["department"]
    runs = int(state.get("rework_runs") or 0)
    workstream = dict(state.get("workstream") or {})
    workstream["department_id"] = department
    handoff = {"ticket_id": state.get("ticket_id"),
               "metadata": state.get("metadata") or {}}
    context = build_generation_context(handoff, workstream)
    context["feedback"] = (state.get("decision") or {}).get("comment") or ""
    draft = generate(context)
    if instruction:
        draft = apply_arbiter_rules(draft, instruction,
                                    state.get("metadata") or {})
    evaluation = evaluate(draft, {
        "key_aspects": workstream.get("key_aspects") or [],
        "client_country": (state.get("metadata") or {}).get("client_country"),
        "department_id": department,
    })
    evaluation["section_id"] = state.get("section_id")
    evaluation["department_id"] = department
    evaluation["iterations"] = runs + 1
    exhausted = runs + 1 >= int(state.get("max_iterations")
                                or default_max_iterations())
    return {
        "draft": draft,
        "evaluation": evaluation,
        "iteration_count": runs + 1,
        "rework_runs": runs + 1,
        "rework_pending": False,
        # §7 currency-mismatch: rechazar si no se resuelve tras el límite.
        "arbitration_blocked": bool(
            instruction is not None
            and instruction.get("trigger") == TRIGGER_CURRENCY_MISMATCH
            and not evaluation.get("overall_pass")
            and exhausted),
        "iteration_limit_reached": exhausted,
        "approval_status": "cambios_solicitados",
    }


def rework_department(state: DepartmentApprovalState,
                      config: RunnableConfig) -> dict[str, Any]:
    """Ciclo restante: vuelve al generador/evaluador de la Parte 2 (Punto A).

    Nodo SEPARADO de ``review`` por una propiedad de langgraph verificada con
    prototipos: los writes de un nodo que termina en ``interrupt`` NO se
    persisten en el checkpoint. Si el rework y la pausa ocurrieran en el mismo
    nodo, el coordinador leería borradores obsoletos y el arbitraje §7 no se
    dispararía. Al dividirlos, el borrador regenerado queda persistido en un
    superstep previo a la interrupción.

    Aquí corren los guardrails automáticos (§5/§7); ``review`` solo pausa
    para el juicio humano.
    """
    options = config.get("configurable") or {}
    trace = options.get("rfp_trace") or (lambda *_args, **_kwargs: None)
    generate = options.get("rfp_generate") or generate_section
    evaluate = options.get("rfp_evaluate") or evaluate_section
    max_iterations = int(options.get("rfp_max_iterations")
                          or default_max_iterations())
    department = state["department"]
    outputs: dict[str, Any] = {"max_iterations": max_iterations}
    runs = int(state.get("rework_runs") or 0)
    evaluation = state.get("evaluation") or {}
    instruction = (state.get("rework_instructions") or {}).get(department)
    needs_rework = bool(state.get("rework_pending")) or not state.get("draft")
    returns_breach = RETURNS_RULE in _violation_flags(
        {"evaluation_results": evaluation})

    # Guardrail: límite de iteraciones del ciclo restante. No se vuelve a
    # invocar al generador; se conserva el borrador anterior y la decisión
    # humana se ofrece igualmente.
    if needs_rework and runs >= max_iterations:
        outputs.update({
            "rework_pending": False,
            "iteration_limit_reached": True,
            "approval_status": state.get("approval_status")
            if state.get("approval_status") != "pendiente"
            else "cambios_solicitados",
        })
        trace(make_node_trace("rework_generator", department,
                              {"action": "iteration_limit"},
                              {"rework_runs": runs}))
        return outputs

    # Rechazo humano (request_changes/rechazo) o arbitraje ⇒ re-trabajo;
    # si la sección aún embebe devoluciones <48 h (§5) se fuerza la regla
    # del árbitro aunque no haya decisión humana pendiente.
    forced_returns = None
    if returns_breach and runs < max_iterations:
        forced_returns = {
            "trigger": TRIGGER_RETURNS_SLA_BREACH,
            "arbiter": ARBITERS[TRIGGER_RETURNS_SLA_BREACH],
            "action": ARBITER_ACTIONS[TRIGGER_RETURNS_SLA_BREACH],
        }
    if needs_rework or forced_returns:
        chosen = instruction or forced_returns
        human_requested = bool(state.get("rework_pending"))
        outputs.update(_run_rework_cycle(state, generate, evaluate, chosen))
        if not human_requested:
            # Primer ciclo (arranque o guardrail automático): la sección queda
            # "pendiente" de juicio humano, nunca "cambios_solicitados"
            # (esa etiqueta exige una decisión humana previa).
            outputs["approval_status"] = "pendiente"
        trace(make_node_trace(
            "rework_generator", department,
            {"feedback": (state.get("decision") or {}).get("comment"),
             "trigger": (chosen or {}).get("trigger"),
             "rework_runs": outputs.get("rework_runs")},
            {"draft_length": len(outputs.get("draft") or ""),
             "overall_pass": (outputs.get("evaluation") or {}).get(
                 "overall_pass")}))
        evaluation = outputs.get("evaluation") or evaluation

        # Guardrail §7: arbitraje agotado en currency-mismatch ⇒ rechazo
        # terminal (sin ofrecer aprobación).
        if (outputs.get("arbitration_blocked")
                and not evaluation.get("overall_pass", True)):
            outputs["approval_status"] = "rechazado"
            outputs["arbitration_blocked"] = True
            outputs["rework_pending"] = False
            trace(make_node_trace("review_department", department,
                                  {"action": "arbitration_exhausted"}, outputs))
            return outputs

        # El ciclo aún embebe devoluciones <48 h y no fue el árbitro quien
        # lo reescribió: un ciclo forzado adicional dentro del límite.
        if (RETURNS_RULE in _violation_flags({"evaluation_results": evaluation})
                and (chosen or {}).get("trigger")
                != TRIGGER_RETURNS_SLA_BREACH
                and int(outputs.get("rework_runs") or 0) < max_iterations):
            outputs.update(_run_rework_cycle(
                {**state,
                 "rework_runs": int(outputs.get("rework_runs") or 0),
                 "decision": state.get("decision") or {}},
                generate, evaluate, forced_returns))
            trace(make_node_trace("review_department", department,
                                  {"action": "force_request_changes",
                                   "trigger": TRIGGER_RETURNS_SLA_BREACH},
                                  {"rework_runs": outputs.get("rework_runs")}))
    return outputs


def review_department(state: DepartmentApprovalState,
                      config: RunnableConfig) -> dict[str, Any]:
    """Nodo de ``interrupt``: pausa SOLO la rama del departamento.

    El checkpoint con la interrupción se persiste ANTES de devolver el
    control; los demás departamentos siguen en paralelo (hilo con thread_id
    namespaced ``rfp-{ticket}:{dept}``). La respuesta humana se valida en
    ``ApprovalSession.resume`` antes de reinsertarla vía ``Command(resume)``.
    """
    options = config.get("configurable") or {}
    trace = options.get("rfp_trace") or (lambda *_args, **_kwargs: None)
    department = state["department"]
    outputs: dict[str, Any] = {}

    # Rechazo terminal por arbitraje agotado (§7): no se ofrece aprobación.
    if state.get("arbitration_blocked"):
        outputs.update({
            "approval_status": "rechazado",
            "rework_pending": False,
            "iteration_limit_reached": bool(
                state.get("iteration_limit_reached")),
        })
        trace(make_node_trace("review_department", department,
                              {"action": "arbitration_exhausted"},
                              {"rechazado": True}))
        return outputs

    draft = state.get("draft") or ""
    evaluation = state.get("evaluation") or {}
    flags = set(_violation_flags({"evaluation_results": evaluation}))
    round_number = int(state.get("round") or 0) + 1
    workstream = state.get("workstream") or {}
    payload = {
        "department_id": department,
        "approver": state.get("approver") or DEPARTMENTS[department]["approver"],
        "section_id": state.get("section_id"),
        "draft_content": draft,
        "evaluation": evaluation,
        "open_questions": workstream.get("open_questions") or [],
        "flags": sorted(flags | set(_violation_flags(
            {"evaluation_results": evaluation}))),
        "needs_human_review": not evaluation.get("overall_pass", True),
        "iteration_limit_reached": bool(
            state.get("iteration_limit_reached")),
        "round": round_number,
    }
    outputs["round"] = round_number
    trace(make_node_trace("review_department", department,
                          {"action": "await_human_decision",
                           "round": round_number},
                          {"interrupted": True}))
    # El checkpoint de esta superstep (con el interrupt) se persiste ANTES de
    # devolver el control: langgraph guarda el checkpoint y devuelve la pausa.
    decision: dict[str, Any] = interrupt(payload)

    if decision.get("decision") == DECISION_APROBAR:
        outputs["approval_status"] = "aprobado"
        outputs["rework_pending"] = False
        outputs["iteration_limit_reached"] = False
    else:
        # rechazar / request_changes → vuelven al generador Parte 2
        # (mismo ticket y mismo thread), en el superstep siguiente.
        outputs["approval_status"] = (
            "rechazado" if decision.get("decision") == DECISION_RECHAZAR
            else "cambios_solicitados")
        outputs["rework_pending"] = True
    outputs["decision"] = decision
    trace(make_node_trace("human_decision", department,
                          {"round": round_number},
                          {"decision": decision.get("decision"),
                           "approver": decision.get("approver"),
                           "status": outputs["approval_status"]}))
    return outputs


def build_department_graph() -> StateGraph:
    """Grafo de aprobación de UN departamento (se compila por thread)."""
    builder = StateGraph(DepartmentApprovalState)
    builder.add_node("rework", rework_department)
    builder.add_node("review", review_department)
    builder.add_edge(START, "rework")
    builder.add_edge("rework", "review")
    builder.add_edge("review", END)
    return builder


def detect_conflict_node(state: CoordinatorState) -> dict[str, Any]:
    """Señala conflictos §7 sobre estado estructurado (campos tipados)."""
    metadata = state.get("sections_metadata") or {}
    typed_sections = [
        {"department_id": dept,
         "draft_content": section.get("draft", ""),
         "evaluation_results": section.get("evaluation"),
         "return_sla_breach": section.get("return_sla_breach"),
         "capacity_shortfall": section.get("capacity_shortfall"),
         "volume_assumption": section.get("volume_assumption"),
         "open_questions": section.get("open_questions")}
        for dept, section in (state.get("sections") or {}).items()
    ]
    conflicts = detect_conflicts({"metadata": metadata}, typed_sections)
    return {
        "conflicts": conflicts,
        "decision": "arbitrate" if conflicts else "continue",
    }


def arbitrate_node(state: CoordinatorState) -> dict[str, Any]:
    """Nodo de arbitraje dedicado: aplica el árbitro fijo §7 (nunca un LLM).

    Por defecto la resolución es determinista (``ARBITER_ACTIONS``); con
    ``RFP_ARBITER_MODE=human`` deja la instrucción lista para que el
    responsable nombrado (Miguel Torres) la ejecute. Los agentes solo señalan:
    este nodo es el único que resuelve. Si los conflictos persisten tras el
    límite de iteraciones se marca ``arbitration_exhausted`` (§7:
    currency-mismatch se rechaza si no se resuelve).
    """
    rounds = int(state.get("arbitration_rounds") or 0) + 1
    limit = default_max_iterations()
    out: dict[str, Any] = {"arbitration_rounds": rounds,
                           "decision": "rework"}
    if rounds > limit:
        blocked: dict[str, Any] = {}
        for conflict in state.get("conflicts") or []:
            if conflict["trigger"] == TRIGGER_CURRENCY_MISMATCH:
                for dept in conflict["departments"]:
                    blocked[dept] = {
                        "trigger": conflict["trigger"],
                        "arbiter": ARBITERS[conflict["trigger"]],
                        "action": ARBITER_ACTIONS[conflict["trigger"]],
                    }
        out["arbitration_exhausted"] = {"blocked_departments": sorted(blocked),
                                        "instructions": blocked}
    return out


def check_ready_node(state: CoordinatorState) -> dict[str, Any]:
    """Aprueba el cierre SOLO con sign-off de todos y sin conflictos."""
    sections = state.get("sections") or {}
    approved = bool(sections) and all(
        section.get("status") == "aprobado" for section in sections.values())
    pending = sorted(
        dept for dept, section in sections.items()
        if section.get("status") != "aprobado")
    clean = not state.get("conflicts") and not state.get("arbitration_exhausted")
    return {"decision": "finalize" if (approved and clean) else "wait"}


def _route_after_detect(state: CoordinatorState) -> str:
    return "arbitrate" if state.get("decision") == "arbitrate" else "check"


def _route_after_check(state: CoordinatorState) -> str:
    return "finalize" if state.get("decision") == "finalize" else "wait"


def build_final_document(ticket_id: str, metadata: dict[str, Any],
                         sections: list[dict[str, Any]]) -> dict[str, Any]:
    """Consolida el documento final (BRIEFING §2.3 FinalDocument).

    Se dispara SOLO con el sign-off de todos los departamentos activos
    (garantiza el coordinador vía ``_route_after_check``). Moneda por
    ``client_country`` (§5); secciones en el orden fijo de §2.1.
    """
    currency = (expected_currency(metadata.get("client_country"))
                or metadata.get("currency"))
    ordered = sorted(sections,
                     key=lambda s: (DEPT_ORDER.index(s["department_id"])
                                    if s.get("department_id") in DEPT_ORDER
                                    else 99, s.get("department_id") or ""))
    client = metadata.get("client_name") or "cliente"
    parts = [f"# Propuesta TrackFlow para {client}\n"]
    for section in ordered:
        parts.append((section.get("draft_content") or "").rstrip())
    content = "\n\n".join(part for part in parts if part)
    return {
        "ticket_id": ticket_id,
        "sections": [
            {
                "department_id": section.get("department_id"),
                "section_id": section.get("section_id"),
                "approver": section.get("approver"),
                "draft_content": section.get("draft_content"),
                "approval_status": section.get("approval_status", "aprobado"),
                "approved_at": section.get("approved_at"),
            }
            for section in ordered
        ],
        "currency": currency,
        "generated_at": _utc_now(),
        "content": content,
        "provisional": any(section.get("approval_status") != "aprobado"
                           for section in ordered),
    }


def finalize_node(state: CoordinatorState) -> dict[str, Any]:
    metadata = state.get("sections_metadata") or {}
    sections = [
        {"department_id": dept,
         "section_id": section.get("section_id"),
         "approver": section.get("approver"),
         "draft_content": section.get("draft"),
         "evaluation_results": section.get("evaluation"),
         "approval_status": "aprobado",
         "needs_human_review": section.get("needs_human_review", False),
         "approved_at": section.get("approved_at")}
        for dept, section in sorted(
            (state.get("sections") or {}).items(),
            key=lambda item: (DEPT_ORDER.index(item[0])
                              if item[0] in DEPT_ORDER else 99, item[0]))
    ]
    document = build_final_document(state.get("ticket_id") or "",
                                    metadata, sections)
    return {"final_document": document}


def build_coordinator_graph() -> StateGraph:
    builder = StateGraph(CoordinatorState)
    builder.add_node("detect", detect_conflict_node)
    builder.add_node("arbitrate", arbitrate_node)
    builder.add_node("check", check_ready_node)
    builder.add_node("finalize", finalize_node)
    builder.add_node("wait", lambda _state: {})
    builder.add_edge(START, "detect")
    builder.add_conditional_edges("detect", _route_after_detect,
                                  ["arbitrate", "check"])
    builder.add_edge("arbitrate", "check")
    builder.add_conditional_edges("check", _route_after_check,
                                  ["finalize", "wait"])
    builder.add_edge("finalize", END)
    builder.add_edge("wait", END)
    return builder


# --------------------------------------------------------------------------
# Sesión de aprobación: checkpointer persistente + resume explícito
# --------------------------------------------------------------------------
class ApprovalSession:
    """Orquesta los grafos de aprobación con un checkpointer persistente."""

    def __init__(self, saver: SqliteSaver,
                 trace_sink: Callable[[str, dict[str, Any]], None] | None = None,
                 generate: Callable[[dict[str, Any]], str] | None = None,
                 evaluate: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
                 max_iterations: int | None = None) -> None:
        self._saver = saver
        self._dept_apps: dict[str, CompiledStateGraph] = {}
        self._dept_lock = threading.Lock()
        self._coord_app: CompiledStateGraph | None = None
        self._trace_sink = trace_sink
        self._generate = generate
        self._evaluate = evaluate
        self._max_iterations = max_iterations or default_max_iterations()

    # --- grafos -----------------------------------------------------------
    def _dept_app(self, department: str) -> CompiledStateGraph:
        with self._dept_lock:
            app = self._dept_apps.get(department)
            if app is None:
                app = build_department_graph().compile(checkpointer=self._saver)
                self._dept_apps[department] = app
            return app

    @property
    def coordinator(self) -> CompiledStateGraph:
        if self._coord_app is None:
            self._coord_app = build_coordinator_graph().compile(
                checkpointer=self._saver)
        return self._coord_app

    # --- configs (Punto C: thread_id namespaced) --------------------------
    def _dept_config(self, ticket_id: str, department: str) -> dict[str, Any]:
        # Los nodos emiten trace(entry); el sink persistente recibe
        # (ticket_id, entry): se adapta aquí, en un único punto.
        sink = self._trace_sink
        node_trace = (None if sink is None
                      else (lambda entry: self._trace(ticket_id, entry)))
        return {"configurable": {
            "thread_id": department_thread_id(ticket_id, department),
            "rfp_trace": node_trace,
            "rfp_generate": self._generate,
            "rfp_evaluate": self._evaluate,
            "rfp_max_iterations": self._max_iterations,
        }}

    def _coord_config(self, ticket_id: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": thread_id(ticket_id)}}

    # --- trazabilidad -----------------------------------------------------
    def _trace(self, ticket_id: str, entry: dict[str, Any]) -> None:
        if self._trace_sink is None:
            return
        try:
            self._trace_sink(ticket_id, entry)
        except Exception:
            logger.exception("Trace sink failed ticket_id=%s", ticket_id)
            # Permite que Celery reciba el fallo y pueda reintentar la tarea.
            raise

    # --- payload inicial de una rama ---------------------------------------
    def _initial_state(self, ticket_id: str, department: str,
                       section: dict[str, Any],
                       workstream: dict[str, Any],
                       metadata: dict[str, Any],
                       instruction: dict[str, Any] | None) -> dict[str, Any]:
        return {
            "ticket_id": ticket_id,
            "department": department,
            "approver": section.get("approver")
            or workstream.get("approver")
            or DEPARTMENTS.get(department, {}).get("approver", ""),
            "workstream": workstream or {"department_id": department},
            "metadata": metadata,
            "section_id": section.get("section_id") or f"{ticket_id}:{department}",
            "draft": section.get("draft_content") or "",
            "evaluation": section.get("evaluation_results") or {},
            "iteration_count": section.get("iteration_count") or 0,
            "rework_runs": section.get("rework_iteration_count") or 0,
            "rework_pending": bool(instruction),
            "rework_instructions": {department: instruction} if instruction else {},
            "arbitration_blocked": bool(section.get("arbitration_blocked")),
            "approval_status": section.get("approval_status", "pendiente"),
            "max_iterations": self._max_iterations,
        }

    # --- Punto de entrada: arranque de aprobaciones -----------------------
    def start_approvals(self, ticket_id: str,
                        handoff: dict[str, Any]) -> dict[str, Any]:
        """Arranca las ramas de TODOS los departamentos activos en paralelo.

        Aplica primero el arbitraje inicial (estado estructurado del handoff)
        y luego pausa cada rama en su ``interrupt``. Devuelve los interrupts
        pendientes por departamento y las instrucciones del árbitro.
        """
        metadata = dict(handoff.get("metadata") or {})
        conflicts = detect_conflicts(handoff)
        instructions: dict[str, dict[str, Any]] = {}
        for conflict in conflicts:
            for dept in conflict["departments"]:
                instructions[dept] = {
                    "trigger": conflict["trigger"],
                    "arbiter": ARBITERS[conflict["trigger"]],
                    "action": ARBITER_ACTIONS[conflict["trigger"]],
                }
        self._trace(ticket_id, make_node_trace(
            "detect_conflicts", None,
            {"sections": sorted({s.get("department_id")
                                 for s in handoff.get("sections") or []})},
            {"conflicts": conflicts, "instructions": instructions}))

        workstreams = {
            ws["department_id"]: ws
            for ws in (handoff.get("department_workstreams") or [])}
        sections_by_dept = {s["department_id"]: s
                            for s in handoff.get("sections") or []}
        departments = sorted(
            set(sections_by_dept) | set(workstreams),
            key=lambda d: (DEPT_ORDER.index(d) if d in DEPT_ORDER else 99, d))

        def _start(dept: str) -> str:
            initial = self._initial_state(
                ticket_id, dept, sections_by_dept.get(dept) or {},
                workstreams.get(dept) or {}, metadata,
                instructions.get(dept))
            app = self._dept_app(dept)
            app.invoke(initial, self._dept_config(ticket_id, dept))
            return dept

        # Ramas reales en paralelo: cada hilo pausa SOLO su propio grafo.
        with ThreadPoolExecutor(max_workers=max(1, len(departments))) as pool:
            list(pool.map(_start, departments))

        pending = self.pending_interrupts(ticket_id, departments)
        self._trace(ticket_id, make_node_trace(
            "start_approvals", None, {"departments": departments},
            {"interrupts": {dept: [i["id"] for i in items]
                            for dept, items in pending.items()},
             "instructions": instructions}))
        result = self._sync_sections(ticket_id, metadata, handoff, departments)
        return {"ticket_id": ticket_id, "departments": departments,
                "pending": pending, "instructions": instructions,
                "conflicts": conflicts, "coordinator": result,
                "complete": self.is_complete(ticket_id)}

    # --- consultas --------------------------------------------------------
    def _active_departments(self, ticket_id: str) -> list[str]:
        state = self.coordinator.get_state(self._coord_config(ticket_id))
        values = state.values or {}
        listed = list(values.get("active_departments") or [])
        if listed:
            return listed
        prefix = f"rfp-{ticket_id}:"
        seen: set[str] = set()
        try:
            for checkpoint_tuple in self._saver.list(None):
                configurable = ((checkpoint_tuple.config or {}).get("configurable")
                                or {})
                tid = str(configurable.get("thread_id") or "")
                if tid.startswith(prefix):
                    seen.add(tid[len(prefix):])
        except Exception:  # pragma: no cover - list() es best-effort
            logger.exception("checkpoint list failed ticket_id=%s", ticket_id)
        return sorted(seen, key=lambda d: (DEPT_ORDER.index(d)
                                           if d in DEPT_ORDER else 99, d))

    def pending_interrupts(self, ticket_id: str,
                           departments: list[str] | None = None
                           ) -> dict[str, list[dict[str, Any]]]:
        """Interrupciones pendientes por departamento (threadnamespaced)."""
        departments = (departments if departments is not None
                       else self._active_departments(ticket_id))
        result: dict[str, list[dict[str, Any]]] = {}
        for dept in departments:
            state = self._dept_app(dept).get_state(
                self._dept_config(ticket_id, dept))
            items = [{"id": interrupt.id, "value": interrupt.value,
                      "department": dept}
                     for task in (state.tasks or [])
                     for interrupt in task.interrupts]
            if items:
                result[dept] = items
        return result

    def approval_state(self, ticket_id: str) -> dict[str, Any]:
        """Estado de aprobación por departamento (para API/UI)."""
        out: dict[str, Any] = {}
        for dept in self._active_departments(ticket_id):
            state = self._dept_app(dept).get_state(
                self._dept_config(ticket_id, dept))
            values = state.values or {}
            interrupt_value = next(
                (i.value for task in (state.tasks or [])
                 for i in task.interrupts), None)
            out[dept] = {
                "department_id": dept,
                "approver": values.get("approver")
                or DEPARTMENTS.get(dept, {}).get("approver", ""),
                "approval_status": values.get("approval_status", "pendiente"),
                "decision": values.get("decision"),
                "round": values.get("round", 0),
                "rework_runs": values.get("rework_runs", 0),
                "arbitration_blocked": bool(values.get("arbitration_blocked")),
                "iteration_limit_reached": bool(
                    values.get("iteration_limit_reached")),
                "pending_interrupt": bool(interrupt_value),
                "interrupt": interrupt_value,
                "draft": values.get("draft") or "",
                "evaluation": values.get("evaluation") or {},
                "thread_id": department_thread_id(ticket_id, dept),
            }
        return out

    def final_document(self, ticket_id: str) -> dict[str, Any] | None:
        state = self.coordinator.get_state(self._coord_config(ticket_id))
        return (state.values or {}).get("final_document")

    def is_complete(self, ticket_id: str) -> bool:
        document = self.final_document(ticket_id)
        return bool(document and document.get("content"))

    # --- Punto de entrada: resume explícito (nunca reinicio completo) -----
    def resume(self, ticket_id: str, department: str,
               interrupt_id: str, payload: Any) -> dict[str, Any]:
        """Inserta la decisión humana validada vía ``Command(resume=...)``."""
        decision = validate_decision(payload, department)
        config = self._dept_config(ticket_id, department)
        app = self._dept_app(department)
        state = app.get_state(config)
        known = {i.id for task in (state.tasks or []) for i in task.interrupts}
        if interrupt_id not in known:
            raise ApprovalError(
                f"{department} no tiene una decisión pendiente con id "
                f"{interrupt_id} en este ticket.")
        values = state.values or {}
        if (values.get("arbitration_blocked")
                and decision.get("decision") == DECISION_APROBAR):
            raise ApprovalError(
                "La sección fue rechazada por arbitraje tras agotar el límite "
                "de iteraciones; no admite aprobación.")
        self._trace(ticket_id, make_node_trace(
            "resume", department, {"interrupt_id": interrupt_id},
            {"decision": decision.get("decision")}))
        app.invoke(Command(resume={interrupt_id: decision}), config)
        # rechazar / request_changes → vuelven al generador Parte 2.
        values = (app.get_state(config).values or {})
        if values.get("rework_pending"):
            self._reenter_department(ticket_id, department)
        return self._after_department_event(ticket_id, department)

    def _reenter_department(self, ticket_id: str, department: str) -> None:
        """Re-entrada de la rama tras una decisión que exige re-trabajo."""
        app = self._dept_app(dept := department)
        config = self._dept_config(ticket_id, department)
        values = app.get_state(config).values or {}
        initial = {
            "ticket_id": ticket_id,
            "department": department,
            "approver": values.get("approver") or "",
            "workstream": values.get("workstream") or {"department_id": department},
            "metadata": values.get("metadata") or {},
            "section_id": values.get("section_id"),
            "draft": values.get("draft") or "",
            "evaluation": values.get("evaluation") or {},
            "iteration_count": values.get("iteration_count", 0),
            "rework_runs": values.get("rework_runs", 0),
            "rework_pending": True,
            "rework_instructions": values.get("rework_instructions") or {},
            "arbitration_blocked": bool(values.get("arbitration_blocked")),
            "approval_status": values.get("approval_status", "pendiente"),
            "decision": values.get("decision") or {},
            "max_iterations": self._max_iterations,
        }
        self._trace(ticket_id, make_node_trace(
            "reenter_generator", department,
            {"rework_runs": initial["rework_runs"],
             "feedback": (initial["decision"] or {}).get("comment")}, {}))
        app.invoke(initial, config)

    def apply_arbitration(self, ticket_id: str,
                          instructions: dict[str, dict[str, Any]]) -> dict[str, Any]:
        """Re-entrada de departamentos con la resolución del árbitro (§7)."""
        for dept, instruction in (instructions or {}).items():
            app = self._dept_app(dept)
            config = self._dept_config(ticket_id, dept)
            values = app.get_state(config).values or {}
            rework = dict(values.get("rework_instructions") or {})
            rework[dept] = instruction
            initial = {
                "ticket_id": ticket_id,
                "department": dept,
                "approver": values.get("approver") or "",
                "workstream": values.get("workstream")
                or {"department_id": dept},
                "metadata": values.get("metadata") or {},
                "section_id": values.get("section_id") or f"{ticket_id}:{dept}",
                "draft": values.get("draft") or "",
                "evaluation": values.get("evaluation") or {},
                "iteration_count": values.get("iteration_count", 0),
                "rework_runs": values.get("rework_runs", 0),
                "rework_pending": True,
                "rework_instructions": rework,
                "arbitration_blocked": bool(values.get("arbitration_blocked")),
                "approval_status": values.get("approval_status", "pendiente"),
                "decision": values.get("decision") or {},
                "max_iterations": self._max_iterations,
            }
            self._trace(ticket_id, make_node_trace(
                "apply_arbitration", dept, {"instruction": instruction}, {}))
            app.invoke(initial, config)
        return {"instructions": instructions,
                "pending": self.pending_interrupts(ticket_id,
                                                   sorted(instructions or {}))}

    def _block_department(self, ticket_id: str, department: str) -> None:
        """Marca una sección como rechazo terminal por arbitraje agotado (§7)."""
        app = self._dept_app(department)
        config = self._dept_config(ticket_id, department)
        values = app.get_state(config).values or {}
        initial = {
            "ticket_id": ticket_id,
            "department": department,
            "approver": values.get("approver") or "",
            "workstream": values.get("workstream")
            or {"department_id": department},
            "metadata": values.get("metadata") or {},
            "section_id": values.get("section_id"),
            "draft": values.get("draft") or "",
            "evaluation": values.get("evaluation") or {},
            "iteration_count": values.get("iteration_count", 0),
            "rework_runs": max(int(values.get("rework_runs") or 0),
                               self._max_iterations),
            "rework_pending": True,
            "rework_instructions": values.get("rework_instructions") or {},
            "arbitration_blocked": True,
            "approval_status": values.get("approval_status", "pendiente"),
            "decision": values.get("decision") or {},
            "max_iterations": self._max_iterations,
        }
        self._trace(ticket_id, make_node_trace(
            "arbitration_exhausted", department, {}, {"rechazado": True}))
        app.invoke(initial, config)

    def _sync_sections(self, ticket_id: str, metadata: dict[str, Any],
                       handoff: dict[str, Any] | None,
                       departments: list[str] | None = None) -> dict[str, Any]:
        """Actualiza el coordinador con el estado real de las secciones."""
        departments = (departments if departments is not None
                       else self._active_departments(ticket_id))
        sections: dict[str, dict[str, Any]] = {}
        for dept in departments:
            values = (self._dept_app(dept).get_state(
                self._dept_config(ticket_id, dept)).values or {})
            approval = self.approval_state(ticket_id).get(dept) or {}
            sections[dept] = {
                "status": values.get("approval_status", "pendiente"),
                "draft": values.get("draft") or "",
                "evaluation": values.get("evaluation") or {},
                "approver": values.get("approver")
                or DEPARTMENTS.get(dept, {}).get("approver", ""),
                "section_id": values.get("section_id"),
                "needs_human_review": bool(values.get("iteration_limit_reached"))
                or not (values.get("evaluation") or {}).get("overall_pass", True),
                "approved_at": ((values.get("decision") or {}).get("decided_at")
                                if values.get("approval_status") == "aprobado"
                                else None),
                "open_questions": (values.get("workstream") or {}).get(
                    "open_questions") or [],
                "arbitration_blocked": bool(values.get("arbitration_blocked")),
                "pending_interrupt": approval.get("pending_interrupt", False),
            }
        coord_state = self.coordinator.get_state(self._coord_config(ticket_id))
        payload: dict[str, Any] = {
            "ticket_id": ticket_id,
            "active_departments": departments,
            "sections": sections,
            "sections_metadata": dict(metadata),
        }
        if coord_state.values:
            payload["arbitration_rounds"] = int(
                coord_state.values.get("arbitration_rounds") or 0)
            if coord_state.values.get("arbitration_exhausted"):
                payload["arbitration_exhausted"] = coord_state.values[
                    "arbitration_exhausted"]
        result = self.coordinator.invoke(payload, self._coord_config(ticket_id))
        self._trace(ticket_id, make_node_trace(
            "coordinator", None,
            {"sections": {d: s["status"] for d, s in sections.items()}},
            {"decision": result.get("decision"),
             "conflicts": [c["trigger"] for c in result.get("conflicts") or []],
             "final": bool(result.get("final_document"))}))
        return {"sections": sections,
                "decision": result.get("decision"),
                "conflicts": result.get("conflicts") or [],
                "arbitration_rounds": int(result.get("arbitration_rounds") or 0),
                "arbitration_exhausted": result.get("arbitration_exhausted"),
                "final_document": result.get("final_document")}

    def _resolve_conflicts(self, ticket_id: str, metadata: dict[str, Any],
                           handoff: dict[str, Any] | None) -> dict[str, Any]:
        """Aplica el arbitraje hasta resolver (o agotar el límite §7)."""
        result = self._sync_sections(ticket_id, metadata, handoff)
        for _attempt in range(self._max_iterations + 2):
            if not result["conflicts"]:
                return result
            exhausted = result.get("arbitration_exhausted")
            if exhausted:
                for dept in exhausted.get("blocked_departments") or []:
                    self._block_department(ticket_id, dept)
                result = self._sync_sections(ticket_id, metadata, handoff)
                return result
            instructions = {
                dept: {
                    "trigger": conflict["trigger"],
                    "arbiter": ARBITERS[conflict["trigger"]],
                    "action": ARBITER_ACTIONS[conflict["trigger"]],
                }
                for conflict in result["conflicts"]
                for dept in conflict["departments"]}
            self.apply_arbitration(ticket_id, instructions)
            result = self._sync_sections(ticket_id, metadata, handoff)
        return result

    def _after_department_event(self, ticket_id: str,
                                department: str) -> dict[str, Any]:
        """Tras cada decisión: arbitraje si hace falta y cierre si corresponde."""
        values = (self._dept_app(department).get_state(
            self._dept_config(ticket_id, department)).values or {})
        metadata = values.get("metadata") or {}
        result = self._resolve_conflicts(ticket_id, metadata, None)
        pending = self.pending_interrupts(ticket_id)
        complete = self.is_complete(ticket_id)
        return {"ticket_id": ticket_id, "department": department,
                "approval_status": (self.approval_state(ticket_id)
                                    .get(department, {}).get("approval_status")),
                "pending": pending,
                "coordinator_decision": result["decision"],
                "conflicts": result["conflicts"],
                "final_document": result["final_document"],
                "complete": complete}


@contextmanager
def open_approval_env(
    checkpoint_db: Path | str | None = None,
    trace_sink: Callable[[str, dict[str, Any]], None] | None = None,
    generate: Callable[[dict[str, Any]], str] | None = None,
    evaluate: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
    max_iterations: int | None = None,
) -> Iterator[ApprovalSession]:
    """Abre la sesión con checkpointer SqliteSaver PERSISTENTE (nada en memoria).

    La base se crea en ``RFP_APPROVAL_DB`` (por defecto
    ``data/checkpoints/rfp_approval.db``); ``setup()`` crea las tablas y la
    conexión se mantiene viva mientras dura la sesión (patrón de
    services/support_agent/graph.py).
    """
    database_path = Path(checkpoint_db or default_checkpoint_db())
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path, timeout=30,
                                 check_same_thread=False)
    saver = SqliteSaver(connection)
    saver.setup()
    try:
        yield ApprovalSession(saver, trace_sink=trace_sink, generate=generate,
                              evaluate=evaluate, max_iterations=max_iterations)
    finally:
        connection.close()


__all__ = [
    "ApprovalError", "ApprovalSession", "DecisionValidationError",
    "STATUS_ESPERANDO_APROBACION", "STATUS_TERMINADO",
    "TRIGGER_CURRENCY_MISMATCH", "TRIGGER_RETURNS_SLA_BREACH",
    "TRIGGER_VOLUME_VS_CAPACITY", "ARBITERS", "ARBITER_ACTIONS",
    "VALID_DECISIONS", "DECISION_APROBAR", "DECISION_RECHAZAR", "DECISION_CAMBIOS",
    "RETURNS_RULE", "build_coordinator_graph", "build_department_graph",
    "build_final_document", "default_checkpoint_db", "department_thread_id",
    "detect_conflicts", "expected_currency", "make_node_trace",
    "open_approval_env", "thread_id", "validate_decision",
]
