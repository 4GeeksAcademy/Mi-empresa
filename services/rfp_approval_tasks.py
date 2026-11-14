"""Celery tasks for Part 3: human approval and final RFP document closure.

The task resumes from the Part 2 handoff (``response_handoff`` stored when the
ticket left ``generando_borrador``); the PDF is never re-ingested. All agent
logic lives in ``data.pipelines.rfp_intake.approval``; this module only wires
persistence (sections, ticket status, final document and node traces).

Design decisions (Hito 9 Parte 3):

* The ticket sits in ``esperando_aprobación`` while ANY active department is
  still pending; it only reaches ``terminado`` once the consolidator stored
  the final document. No orphan states are invented.
* A rejection / request_changes returns to the Part 2 generator within the
  SAME ticket and thread (``rework_pending`` → ``_reenter_department``), so
  iteration history is never lost.
* The interrupt pauses ONLY its own department branch; other branches keep
  running in parallel threads with their own namespaced checkpoint
  (``rfp-{ticket}:{department}``).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from celery import shared_task
from sqlmodel import Session, select

from database import get_engine
from data.pipelines.rfp_intake.approval import (
    ApprovalError,
    DecisionValidationError,
    STATUS_ESPERANDO_APROBACION,
    STATUS_TERMINADO,
    open_approval_env,
    validate_decision,
)
from data.pipelines.rfp_intake.response import default_max_iterations
from models import DepartmentSectionRecord, RfpNodeTrace, RfpTicket

logger = logging.getLogger("trackflow_rfp")

_SECTION_APPROVAL_STATUSES = {"pendiente", "aprobado", "rechazado",
                              "cambios_solicitados"}


def approval_checkpoint_db() -> Path:
    """Checkpoint SQLite persistente compartido por backend y worker.

    Vive en ``data/checkpoints/rfp_approval.db`` (raíz del monorepo en local,
    ``/app/data/checkpoints`` en contenedor), la misma ruta que usa
    ``default_checkpoint_db`` de approval.py; ambos procesos comparten el
    fichero con un volumen montado, nunca estado en memoria.
    """
    return Path(__file__).resolve().parent.parent / "data" / "checkpoints" / "rfp_approval.db"


def _trace_sink(ticket_id: str, entry: dict[str, Any]) -> None:
    """Callback de trazas: una fila por ejecución de nodo, consultable por ticket."""
    try:
        with Session(get_engine()) as session:
            session.add(RfpNodeTrace(
                ticket_id=UUID(ticket_id),
                node=str(entry.get("node") or "unknown"),
                agent=str(entry.get("agent") or "unknown"),
                department=entry.get("department"),
                input=_jsonable(entry.get("input")),
                output=_jsonable(entry.get("output")),
            ))
            session.commit()
    except Exception:
        logger.exception("Trace persist failed ticket_id=%s node=%s",
                         ticket_id, entry.get("node"))
        # No confirmar el nodo si su traza no se pudo persistir: Celery puede
        # reintentar la tarea y mantener la garantía de auditabilidad.
        raise


def _jsonable(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    try:
        json.dumps(value)
        return value if isinstance(value, dict) else {"value": value}
    except (TypeError, ValueError):
        return {"value": repr(value)}


def _load_handoff(ticket: RfpTicket) -> dict[str, Any] | None:
    """Parte 2 handoff + workstreams de la Parte 1 (mismo ticket, sin reingesta)."""
    if not ticket.response_handoff:
        return None
    handoff = dict(ticket.response_handoff)
    handoff["ticket_id"] = str(ticket.ticket_id)
    if "department_workstreams" not in handoff:
        payload = ticket.synthesizer_payload or {}
        workstreams = ((payload.get("handoff") or {}).get("department_workstreams")
                       or [])
        if workstreams:
            handoff["department_workstreams"] = workstreams
    return handoff


def sync_approval_state(ticket_id: UUID) -> dict[str, Any]:
    """Refleja el estado vivo de los hilos de aprobación en secciones y ticket.

    El ticket queda en ``esperando_aprobación`` mientras haya pendientes y
    pasa a ``terminado`` SOLO cuando el documento final está guardado.
    """
    from data.pipelines.rfp_intake.approval import thread_id as coordinator_thread

    state: dict[str, Any] = {}
    final_document: dict[str, Any] | None = None
    interrupts: dict[str, list[str]] = {}
    checkpoint = approval_checkpoint_db()
    if checkpoint.exists():
        with open_approval_env(checkpoint, trace_sink=_trace_sink) as approval:
            state = approval.approval_state(str(ticket_id))
            final_document = approval.final_document(str(ticket_id))
            interrupts = {dept: [item["id"] for item in items]
                          for dept, items in approval.pending_interrupts(
                              str(ticket_id)).items()}
    with Session(get_engine()) as session:
        ticket = session.get(RfpTicket, ticket_id)
        if ticket is None:
            return state
        sections = session.exec(select(DepartmentSectionRecord).where(
            DepartmentSectionRecord.ticket_id == ticket_id)).all()
        rows = {row.department_id: row for row in sections}
        for dept, info in state.items():
            row = rows.get(dept)
            if row is None:
                continue
            if info.get("approval_status") in _SECTION_APPROVAL_STATUSES:
                row.approval_status = info["approval_status"]
            row.draft_content = info.get("draft") or row.draft_content
            row.evaluation_results = info.get("evaluation") or row.evaluation_results
            row.rework_runs = int(info.get("rework_runs") or 0)
            row.decision = info.get("decision")
            row.arbitration_blocked = bool(info.get("arbitration_blocked"))
            row.needs_human_review = bool(
                info.get("iteration_limit_reached")
                or not (row.evaluation_results or {}).get("overall_pass", True)
                or bool(info.get("pending_interrupt")))
            if info.get("approval_status") == "aprobado":
                row.approved_at = row.approved_at or datetime.now(timezone.utc)
            session.add(row)

        ticket.final_document = final_document
        pending = [dept for dept, info in state.items()
                   if info.get("approval_status") != "aprobado"]
        if final_document and final_document.get("content"):
            ticket.status = STATUS_TERMINADO
        elif state:
            ticket.status = STATUS_ESPERANDO_APROBACION
        ticket.updated_at = datetime.now(timezone.utc)
        session.add(ticket)
        session.commit()
        state["ticket_status"] = ticket.status
        state["pending"] = pending
        state["interrupts"] = interrupts
        state["coordinator_thread"] = coordinator_thread(str(ticket_id))
    return state


def approval_snapshot(ticket_id: UUID) -> dict[str, Any] | None:
    """Snapshot de aprobación para API/UI: datos mínimos por responsable.

    Devuelve sección, evaluación resumida, preguntas abiertas, flags y el
    interrupt pendiente SIN forzar al responsable a releer el documento
    completo. Sincroniza el estado vivo con la base en cada consulta.
    """
    state = sync_approval_state(ticket_id)
    if not state:
        return None
    with Session(get_engine()) as session:
        ticket = session.get(RfpTicket, ticket_id)
        if ticket is None:
            return None
        rows = {row.department_id: row for row in session.exec(
            select(DepartmentSectionRecord).where(
                DepartmentSectionRecord.ticket_id == ticket_id)).all()}
    departments = []
    for dept in sorted(state):
        if not isinstance(state[dept], dict) or "department_id" not in state[dept]:
            continue
        info = state[dept]
        row = rows.get(dept) or {}
        evaluation = info.get("evaluation") or {}
        record_evaluation = getattr(row, "evaluation_results", None) or {}
        compliance = (evaluation.get("compliance")
                      or record_evaluation.get("compliance") or {})
        violations = [
            violation.get("rule_id") or violation.get("id")
            for violation in compliance.get("violations", [])
            if isinstance(violation, dict)
        ]
        open_questions = list(getattr(row, "open_questions", None) or [])
        departments.append({
            "department_id": dept,
            "approver": info.get("approver"),
            "section_id": record_evaluation.get("section_id")
            or f"{ticket_id}:{dept}",
            "approval_status": info.get("approval_status"),
            "decision": info.get("decision"),
            "draft_excerpt": (info.get("draft") or "")[:600],
            "evaluation": {
                "overall_pass": evaluation.get(
                    "overall_pass",
                    record_evaluation.get("overall_pass")),
                "score": evaluation.get("score",
                                        record_evaluation.get("score")),
                "violations": violations,
            },
            "open_questions": open_questions,
            "flags": {
                "needs_human_review": bool(info.get("iteration_limit_reached")
                                           or info.get("arbitration_blocked")
                                           or not (evaluation.get(
                                               "overall_pass",
                                               record_evaluation.get(
                                                   "overall_pass")))),
                "iteration_limit_reached": bool(
                    info.get("iteration_limit_reached")),
                "arbitration_blocked": bool(info.get("arbitration_blocked")),
            },
            "rework_runs": info.get("rework_runs"),
            "round": info.get("round"),
            "pending_interrupt": bool(info.get("pending_interrupt")),
            "interrupt_id": (state.get("interrupts") or {}).get(dept, [None])[0],
            "thread_id": info.get("thread_id"),
        })
    return {
        "ticket_id": str(ticket_id),
        "status": state.get("ticket_status"),
        "pending": state.get("pending"),
        "departments": departments,
        "coordinator_thread": state.get("coordinator_thread"),
        "final_document": ticket.final_document,
        "updated_at": ticket.updated_at.isoformat() if ticket.updated_at else None,
    }


@shared_task(bind=True, name="services.rfp_approval_tasks.start_rfp_approvals_task",
             max_retries=2, acks_late=True)
def start_rfp_approvals_task(self, ticket_id: str) -> dict:
    """Arranca las ramas de aprobación (Parte 3) en paralelo desde el handoff Parte 2."""
    identifier = UUID(ticket_id)
    try:
        with Session(get_engine()) as session:
            ticket = session.get(RfpTicket, identifier)
            if ticket is None:
                raise ValueError("RFP ticket not found")
            if ticket.classification_result is not True:
                return {"ticket_id": ticket_id, "status": ticket.status,
                        "reason": "handoff_missing"}
            handoff = _load_handoff(ticket)
            if not handoff or not handoff.get("sections"):
                return {"ticket_id": ticket_id, "status": ticket.status,
                        "reason": "response_handoff_missing"}
            ticket.status = STATUS_ESPERANDO_APROBACION
            ticket.updated_at = datetime.now(timezone.utc)
            session.add(ticket)
            session.commit()

        with open_approval_env(approval_checkpoint_db(),
                               trace_sink=_trace_sink) as approval:
            started = approval.start_approvals(ticket_id, handoff)

        state = sync_approval_state(identifier)
        return {"ticket_id": ticket_id,
                "status": state.get("ticket_status"),
                "departments": started["departments"],
                "pending": {dept: [i["id"] for i in items]
                            for dept, items in started["pending"].items()},
                "conflicts": started["conflicts"],
                "coordinator_thread": started["coordinator"]}
    except Exception as exc:
        logger.exception("RFP approvals start failed ticket_id=%s error_type=%s",
                         ticket_id, type(exc).__name__)
        raise self.retry(exc=exc, countdown=30)


@shared_task(bind=True, name="services.rfp_approval_tasks.record_rfp_decision_task",
             max_retries=2, acks_late=True)
def record_rfp_decision_task(self, ticket_id: str, department: str,
                             payload: dict) -> dict:
    """Punto de entrada explícito de ``resume``: inserta una decisión humana validada."""
    identifier = UUID(ticket_id)
    try:
        with Session(get_engine()) as session:
            ticket = session.get(RfpTicket, identifier)
            if ticket is None:
                raise ValueError("RFP ticket not found")
            handoff = _load_handoff(ticket)
            if not handoff:
                return {"ticket_id": ticket_id, "status": ticket.status,
                        "reason": "approvals_not_started"}
        # Validación ANTES de tocar el grafo: decisión, aprobador y comentario.
        validate_decision(payload, department)
        if not payload.get("interrupt_id"):
            return {"ticket_id": ticket_id, "department": department,
                    "status": "rejected",
                    "reason": "Falta interrupt_id de la decisión pendiente."}
        with open_approval_env(approval_checkpoint_db(),
                               trace_sink=_trace_sink) as approval:
            approval.resume(ticket_id, department,
                            str(payload.get("interrupt_id") or ""), payload)

        state = sync_approval_state(identifier)
        return {"ticket_id": ticket_id, "department": department,
                "decision": payload.get("decision"),
                "status": state.get("ticket_status"),
                "pending": state.get("pending"),
                "complete": state.get("ticket_status") == STATUS_TERMINADO}
    except (DecisionValidationError, ApprovalError) as exc:
        logger.warning("RFP decision rejected ticket_id=%s dept=%s reason=%s",
                       ticket_id, department, exc)
        return {"ticket_id": ticket_id, "department": department,
                "status": "rejected", "reason": str(exc)}
    except Exception as exc:
        logger.exception("RFP decision failed ticket_id=%s dept=%s error_type=%s",
                         ticket_id, department, type(exc).__name__)
        raise self.retry(exc=exc, countdown=10)