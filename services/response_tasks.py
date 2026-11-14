"""Celery tasks for Part 2: draft generation and evaluation per department.

The task starts only from the Part 1 handoff (``synthesizer_payload`` stored
when the ticket reached ``analisis_completo``); the PDF is never re-ingested.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from celery import shared_task
from sqlmodel import Session, select

from database import get_engine
from data.pipelines.rfp_intake.response import (
    STATUS_ANALISIS_COMPLETO,
    STATUS_EN_EVALUACION,
    STATUS_GENERANDO_BORRADOR,
    run_response_generation,
)
from models import DepartmentSectionRecord, RfpTicket

logger = logging.getLogger("trackflow_rfp")


def _progress_reporter(ticket_id: UUID):
    """Callback que refleja el progreso real en el ticket (estado en tiempo real).

    Un estado se escribe solo cuando cambia: `generando_borrador` mientras el
    generador redacta y `en_evaluación` cuando los evaluadores emiten resultado,
    de modo que el polling de la API ve la fase activa en lugar del estado final.
    Cada aviso abre su propia sesión; un fallo aquí no debe abortar el ciclo.
    """
    state = {"status": None}

    def on_progress(phase: str, payload: dict) -> None:
        target = (STATUS_EN_EVALUACION if phase == "evaluacion"
                  else STATUS_GENERANDO_BORRADOR)
        if state["status"] == target:
            return
        try:
            with Session(get_engine()) as session:
                ticket = session.get(RfpTicket, ticket_id)
                if ticket is None or ticket.status == target:
                    state["status"] = target if ticket else state["status"]
                    return
                ticket.status = target
                ticket.updated_at = datetime.now(timezone.utc)
                session.add(ticket)
                session.commit()
            state["status"] = target
            logger.info("ticket %s -> %s (dept=%s iter=%s)", ticket_id, target,
                        payload.get("department_id"),
                        payload.get("iteration"))
        except Exception:
            logger.exception("Status update failed ticket_id=%s", ticket_id)

    return on_progress


@shared_task(bind=True, name="services.response_tasks.generate_rfp_response_task",
             max_retries=2, acks_late=True)
def generate_rfp_response_task(self, ticket_id: str) -> dict:
    identifier = UUID(ticket_id)
    try:
        with Session(get_engine()) as session:
            ticket = session.get(RfpTicket, identifier)
            if ticket is None:
                raise ValueError("RFP ticket not found")
            handoff = ticket.synthesizer_payload
            if not handoff or ticket.classification_result is not True:
                return {"ticket_id": ticket_id, "status": ticket.status,
                        "reason": "handoff_missing"}
            if ticket.status not in {STATUS_ANALISIS_COMPLETO,
                                     STATUS_GENERANDO_BORRADOR, "en_evaluación",
                                     "needs_human_review"}:
                return {"ticket_id": ticket_id, "status": ticket.status,
                        "reason": "ticket_not_ready"}
            handoff = dict(handoff)
            handoff["ticket_id"] = ticket_id
            ticket.status = STATUS_GENERANDO_BORRADOR
            ticket.updated_at = datetime.now(timezone.utc)
            session.add(ticket)
            session.commit()

        result = run_response_generation(
            handoff, on_progress=_progress_reporter(identifier))

        with Session(get_engine()) as session:
            ticket = session.get(RfpTicket, identifier)
            for section in result["sections"]:
                record = session.exec(select(DepartmentSectionRecord).where(
                    DepartmentSectionRecord.ticket_id == identifier,
                    DepartmentSectionRecord.department_id == section["department_id"],
                )).first()
                if record is None:
                    record = DepartmentSectionRecord(
                        ticket_id=identifier,
                        department_id=section["department_id"],
                        approver=section["approver"],
                    )
                record.draft_content = section["draft_content"]
                record.evaluation_results = section["evaluation_results"]
                record.approval_status = section["approval_status"]
                record.iteration_count = section["iteration_count"]
                record.needs_human_review = section["needs_human_review"]
                record.evaluated_at = datetime.now(timezone.utc)
                session.add(record)
            if ticket is not None:
                ticket.status = result["ticket_status"]
                ticket.response_handoff = result["part3_handoff"]
                ticket.updated_at = datetime.now(timezone.utc)
                session.add(ticket)
            session.commit()
        return {"ticket_id": ticket_id, "status": result["ticket_status"],
                "sections": len(result["sections"])}
    except Exception as exc:
        logger.exception("RFP response generation failed ticket_id=%s error_type=%s",
                         ticket_id, type(exc).__name__)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=2 ** self.request.retries)
        raise