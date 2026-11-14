from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from auth import get_current_user
from auth_models import UserRole
from data.pipelines.rfp_intake.approval import (
    DecisionValidationError,
    validate_decision,
)
from database import get_engine
from models import DepartmentSectionRecord, RfpMetadataRecord, RfpTicket
from services.rfp_approval_tasks import approval_snapshot
from services.rfp_tasks import process_rfp_task
from services.response_tasks import generate_rfp_response_task

router = APIRouter(prefix="/api/rfps", tags=["rfps"])
MAX_PDF_BYTES = 25 * 1024 * 1024
RAW_RFP_DIR = Path(os.environ.get("RFP_RAW_DIR", "/app/data/raw/rfps"))
# Estados desde los que la Parte 3 puede arrancar (resultado de la Parte 2).
APPROVAL_START_STATUSES = {"needs_human_review", "en_evaluación"}
APPROVAL_STATUS = "esperando_aprobación"
TERMINATED_STATUS = "terminado"


def enqueue_rfp(ticket_id: str) -> None:
    process_rfp_task.apply_async(args=[ticket_id], task_id=ticket_id)


def enqueue_response(ticket_id: str) -> None:
    """Parte 2: el router solo despacha; la lógica vive en el pipeline."""
    generate_rfp_response_task.apply_async(args=[ticket_id],
                                           task_id=f"{ticket_id}-response")


def enqueue_approvals(ticket_id: str) -> None:
    """Parte 3: solo se despacha; la lógica vive en services + pipeline."""
    from services.rfp_approval_tasks import start_rfp_approvals_task
    start_rfp_approvals_task.apply_async(args=[ticket_id],
                                         task_id=f"{ticket_id}-approvals")


def enqueue_decision(ticket_id: str, department: str, payload: dict) -> None:
    """Punto de entrada explícito de `resume` (nunca reinicio completo)."""
    from services.rfp_approval_tasks import record_rfp_decision_task
    record_rfp_decision_task.apply_async(
        args=[ticket_id, department, payload],
        task_id=f"{ticket_id}-decision-{department}")


def _ticket_response(ticket: RfpTicket, metadata: RfpMetadataRecord | None, sections: list[DepartmentSectionRecord]) -> dict:
    return {
        "ticket_id": str(ticket.ticket_id),
        "rfp_id": str(ticket.rfp_id),
        "status": ticket.status,
        "created_at": ticket.created_at.isoformat(),
        "accepted_at": ticket.accepted_at.isoformat() if ticket.accepted_at else None,
        "filename": ticket.original_filename,
        "classification": {"is_rfp": ticket.classification_result, "reason": ticket.classification_reason},
        "processing_error": ticket.processing_error,
        "metadata": metadata.model_dump(mode="json") if metadata else None,
        "department_sections": [section.model_dump(mode="json") for section in sections],
        "handoff": ticket.synthesizer_payload,
    }


def _ticket_created_payload(ticket: RfpTicket, metadata: RfpMetadataRecord | None) -> dict:
    """Build the small public payload without exposing the uploaded document."""
    return {
        "ticket_id": str(ticket.ticket_id),
        "rfp_id": str(ticket.rfp_id),
        "client_name": metadata.client_name if metadata else None,
        "client_country": metadata.client_country if metadata else None,
        "services_requested": metadata.services_requested if metadata else [],
        "status": ticket.status,
        "created_at": (ticket.accepted_at or ticket.created_at).isoformat(),
    }


def _new_rfp_tickets(created_after: datetime, ticket_after: UUID) -> list[tuple[RfpTicket, RfpMetadataRecord | None]]:
    with Session(get_engine()) as session:
        tickets = session.exec(
            select(RfpTicket)
            .where(
                RfpTicket.classification_result.is_(True),
                RfpTicket.accepted_at.is_not(None),
                (RfpTicket.accepted_at > created_after)
                | ((RfpTicket.accepted_at == created_after) & (RfpTicket.ticket_id > ticket_after)),
            )
            .order_by(RfpTicket.accepted_at, RfpTicket.ticket_id)
        ).all()
        return [(ticket, session.get(RfpMetadataRecord, ticket.ticket_id)) for ticket in tickets]


async def _rfp_event_stream(created_after: datetime):
    last_created_at = created_after
    last_ticket_id = UUID(int=0)
    last_keep_alive = datetime.now(timezone.utc)
    while True:
        tickets = await asyncio.to_thread(
            _new_rfp_tickets, last_created_at, last_ticket_id
        )
        for ticket, metadata in tickets:
            payload = json.dumps(_ticket_created_payload(ticket, metadata), separators=(",", ":"))
            yield f"id: {ticket.ticket_id}\nevent: rfp_ticket_created\ndata: {payload}\n\n"
            last_created_at, last_ticket_id = ticket.accepted_at, ticket.ticket_id

        now = datetime.now(timezone.utc)
        if (now - last_keep_alive).total_seconds() >= 15:
            yield ": keep-alive\n\n"
            last_keep_alive = now
        await asyncio.sleep(1)


@router.get("/events")
def stream_rfp_tickets(
    since: datetime | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
) -> StreamingResponse:
    """Stream accepted tickets to authenticated backoffice staff."""
    if current_user.get("role") not in {UserRole.ADMIN.value, UserRole.MANAGER.value}:
        raise HTTPException(status_code=403, detail="Se requiere acceso al backoffice.")
    cursor = since or datetime.now(timezone.utc)
    return StreamingResponse(
        _rfp_event_stream(cursor),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("")
def list_rfp_tickets(
    created_after: datetime | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
) -> list[dict]:
    """Return snapshots for staff or owned snapshots for regular users."""
    with Session(get_engine()) as session:
        statement = select(RfpTicket).where(
            RfpTicket.classification_result.is_(True),
            RfpTicket.accepted_at.is_not(None),
        )
        if current_user.get("role") not in {UserRole.ADMIN.value, UserRole.MANAGER.value}:
            statement = statement.where(RfpTicket.owner_id == str(current_user["id"]))
        if created_after is not None:
            statement = statement.where(RfpTicket.accepted_at >= created_after)
        tickets = session.exec(statement.order_by(RfpTicket.accepted_at.desc())).all()
        return [
            {
                **_ticket_response(
                ticket,
                session.get(RfpMetadataRecord, ticket.ticket_id),
                session.exec(
                    select(DepartmentSectionRecord).where(
                        DepartmentSectionRecord.ticket_id == ticket.ticket_id
                    )
                ).all(),
                ),
                "accepted_at": ticket.accepted_at.isoformat() if ticket.accepted_at else None,
            }
            for ticket in tickets
        ]


@router.post("", status_code=202)
async def upload_rfp(file: UploadFile = File(...), current_user: dict = Depends(get_current_user)) -> dict[str, str]:
    filename = Path(file.filename or "").name
    if not filename.lower().endswith(".pdf") or file.content_type not in {"application/pdf", "application/octet-stream", None}:
        raise HTTPException(status_code=400, detail="Adjunta un documento PDF.")
    ticket_id, rfp_id = uuid4(), uuid4()
    owner_id = str(current_user["id"])
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", filename)[:180] or "request.pdf"
    path = RAW_RFP_DIR / owner_id / f"{ticket_id}-{safe_name}"
    path.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    try:
        with path.open("xb") as destination:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_PDF_BYTES:
                    raise HTTPException(status_code=413, detail="El PDF supera el límite de 25 MB.")
                destination.write(chunk)
        if size == 0:
            raise HTTPException(status_code=400, detail="El PDF está vacío.")
    except Exception:
        path.unlink(missing_ok=True)
        raise
    with Session(get_engine()) as session:
        ticket = RfpTicket(ticket_id=ticket_id, rfp_id=rfp_id, owner_id=owner_id,
                           original_filename=safe_name, raw_pdf_path=str(path), status="analizando")
        session.add(ticket)
        session.commit()
    try:
        enqueue_rfp(str(ticket_id))
    except Exception as exc:
        with Session(get_engine()) as session:
            ticket = session.get(RfpTicket, ticket_id)
            if ticket:
                ticket.processing_error = f"Queue publish failed ({type(exc).__name__})"
                ticket.updated_at = datetime.now(timezone.utc)
                session.add(ticket)
                session.commit()
        raise HTTPException(status_code=503, detail={"ticket_id": str(ticket_id), "message": "No se pudo confirmar el encolado."}) from exc
    return {"ticket_id": str(ticket_id), "rfp_id": str(rfp_id), "status": "analizando"}


@router.get("/{ticket_id}")
def get_rfp_ticket(ticket_id: UUID, current_user: dict = Depends(get_current_user)) -> dict:
    with Session(get_engine()) as session:
        ticket = session.get(RfpTicket, ticket_id)
        if ticket is None or ticket.owner_id != str(current_user["id"]):
            raise HTTPException(status_code=404, detail="Ticket no encontrado.")
        metadata = session.get(RfpMetadataRecord, ticket_id)
        sections = session.exec(select(DepartmentSectionRecord).where(DepartmentSectionRecord.ticket_id == ticket_id)).all()
        return _ticket_response(ticket, metadata, sections)


@router.get("/{ticket_id}/analysis")
def get_rfp_analysis(ticket_id: UUID, current_user: dict = Depends(get_current_user)) -> dict:
    """Expose the synthesizer's Part 2 handoff for downstream orchestration."""
    with Session(get_engine()) as session:
        ticket = session.get(RfpTicket, ticket_id)
        if ticket is None or ticket.owner_id != str(current_user["id"]):
            raise HTTPException(status_code=404, detail="Ticket no encontrado.")
        if ticket.status == "analizando":
            raise HTTPException(status_code=409, detail="El análisis todavía está en curso.")
        if ticket.processing_error:
            raise HTTPException(status_code=503, detail="El análisis requiere soporte técnico.")
        return ticket.synthesizer_payload or {
            "ticket_id": str(ticket.ticket_id), "status": ticket.status,
            "classification": {"is_rfp": ticket.classification_result, "reason": ticket.classification_reason},
        }


@router.post("/{ticket_id}/response", status_code=202)
def start_rfp_response(ticket_id: UUID, current_user: dict = Depends(get_current_user)) -> dict:
    """Handoff Parte 1 → Parte 2: solo se lanza desde `analisis_completo`."""
    with Session(get_engine()) as session:
        ticket = session.get(RfpTicket, ticket_id)
        if ticket is None or ticket.owner_id != str(current_user["id"]):
            raise HTTPException(status_code=404, detail="Ticket no encontrado.")
        if ticket.status != "analisis_completo":
            raise HTTPException(status_code=409,
                                detail=f"El ticket está en estado {ticket.status}; "
                                       "la generación parte de analisis_completo.")
        if not ticket.synthesizer_payload:
            raise HTTPException(status_code=409, detail="Falta el handoff del synthesizer.")
        # El estado se persiste aquí para que el polling no dependa del worker.
        ticket.status = "generando_borrador"
        ticket.updated_at = datetime.now(timezone.utc)
        session.add(ticket)
        session.commit()
    try:
        enqueue_response(str(ticket_id))
    except Exception as exc:
        raise HTTPException(status_code=503, detail={"ticket_id": str(ticket_id),
                                                    "message": "No se pudo confirmar el encolado."}) from exc
    return {"ticket_id": str(ticket_id), "status": "generando_borrador"}


@router.get("/{ticket_id}/response")
def get_rfp_response(ticket_id: UUID, current_user: dict = Depends(get_current_user)) -> dict:
    """Handoff Parte 2 → Parte 3: borradores + EvaluationResult por departamento."""
    with Session(get_engine()) as session:
        ticket = session.get(RfpTicket, ticket_id)
        if ticket is None or ticket.owner_id != str(current_user["id"]):
            raise HTTPException(status_code=404, detail="Ticket no encontrado.")
        sections = session.exec(select(DepartmentSectionRecord).where(
            DepartmentSectionRecord.ticket_id == ticket_id)).all()
        return {
            "ticket_id": str(ticket.ticket_id),
            "status": ticket.status,
            "handoff": ticket.response_handoff,
            "sections": [
                {
                    "department_id": section.department_id,
                    "approver": section.approver,
                    "draft_content": section.draft_content,
                    "evaluation_results": section.evaluation_results,
                    "approval_status": section.approval_status,
                    "iteration_count": section.iteration_count,
                    "needs_human_review": section.needs_human_review,
                }
                for section in sections
            ],
        }


# --------------------------------------------------------------------------
# Parte 3: aprobación humana y cierre del documento
# --------------------------------------------------------------------------
def _owned_ticket(ticket_id: UUID, current_user: dict) -> RfpTicket:
    with Session(get_engine()) as session:
        ticket = session.get(RfpTicket, ticket_id)
        if ticket is None or ticket.owner_id != str(current_user["id"]):
            raise HTTPException(status_code=404, detail="Ticket no encontrado.")
        return ticket


@router.post("/{ticket_id}/approvals", status_code=202)
def start_rfp_approvals(ticket_id: UUID, current_user: dict = Depends(get_current_user)) -> dict:
    """Handoff Parte 2 → Parte 3: ramas de aprobación en paralelo por depto."""
    previous_status: str
    with Session(get_engine()) as session:
        ticket = session.get(RfpTicket, ticket_id)
        if ticket is None or ticket.owner_id != str(current_user["id"]):
            raise HTTPException(status_code=404, detail="Ticket no encontrado.")
        if ticket.status == APPROVAL_STATUS:
            raise HTTPException(status_code=409, detail="Las aprobaciones ya están en curso.")
        if ticket.status == TERMINATED_STATUS:
            raise HTTPException(status_code=409, detail="El ticket ya está terminado.")
        if ticket.status not in APPROVAL_START_STATUSES:
            raise HTTPException(
                status_code=409,
                detail=f"El ticket está en estado {ticket.status}; la aprobación "
                       "parte de las secciones evaluadas (Parte 2).")
        if not ticket.response_handoff:
            raise HTTPException(status_code=409, detail="Falta el handoff de la Parte 2.")
        if ticket.classification_result is not True:
            raise HTTPException(status_code=409,
                                detail="Solo se pueden aprobar RFPs clasificadas como válidas.")
        # El estado se persiste aquí para que el polling no dependa del worker.
        previous_status = ticket.status
        ticket.status = APPROVAL_STATUS
        ticket.updated_at = datetime.now(timezone.utc)
        session.add(ticket)
        session.commit()
    try:
        enqueue_approvals(str(ticket_id))
    except Exception as exc:
        # Evita dejar el ticket en un estado que rechace el reintento cuando el
        # broker no confirmó la publicación. No pisa un cambio hecho por worker.
        with Session(get_engine()) as session:
            ticket = session.get(RfpTicket, ticket_id)
            if ticket is not None and ticket.status == APPROVAL_STATUS:
                ticket.status = previous_status
                ticket.updated_at = datetime.now(timezone.utc)
                session.add(ticket)
                session.commit()
        raise HTTPException(status_code=503, detail={"ticket_id": str(ticket_id),
                                                    "message": "No se pudo confirmar el encolado."}) from exc
    return {"ticket_id": str(ticket_id), "status": APPROVAL_STATUS}


@router.get("/{ticket_id}/approvals")
def get_rfp_approvals(ticket_id: UUID, current_user: dict = Depends(get_current_user)) -> dict:
    """Snapshot mínimo por responsable: sección, evaluación, flags e interrupt."""
    _owned_ticket(ticket_id, current_user)
    snapshot = approval_snapshot(ticket_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Las aprobaciones aún no han arrancado.")
    return snapshot


@router.post("/{ticket_id}/approvals/{department}")
def record_rfp_decision(ticket_id: UUID, department: str, payload: dict,
                        current_user: dict = Depends(get_current_user)) -> dict:
    """Punto de entrada explícito del `resume`: aprueba/rechaza una sección.

    El router solo valida y despacha; la validación profunda (decisión, aprobador
    fijo del briefing y comentario obligatorio) y el `Command(resume=...)` viven
    en services/rfp_approval_tasks + data/pipelines/rfp_intake/approval.
    """
    ticket = _owned_ticket(ticket_id, current_user)
    if ticket.status != APPROVAL_STATUS:
        raise HTTPException(status_code=409,
                            detail="No hay un ciclo de aprobación activo para este ticket.")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Payload inválido.")
    if payload.get("decision") not in {"aprobar", "rechazar", "request_changes"}:
        raise HTTPException(status_code=400,
                            detail="La decisión debe ser aprobar, rechazar o request_changes.")
    if not payload.get("interrupt_id"):
        raise HTTPException(status_code=400, detail="Falta interrupt_id de la decisión pendiente.")
    try:
        validate_decision(payload, department)
    except DecisionValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        enqueue_decision(str(ticket_id), department, payload)
    except Exception as exc:
        raise HTTPException(status_code=503, detail={"ticket_id": str(ticket_id),
                                                    "message": "No se pudo confirmar el encolado."}) from exc
    return {"ticket_id": str(ticket_id), "department": department,
            "decision": payload["decision"], "status": APPROVAL_STATUS}


@router.get("/{ticket_id}/final-document")
def get_rfp_final_document(ticket_id: UUID, current_user: dict = Depends(get_current_user)) -> dict:
    """Documento final consolidado: solo existe con todas las secciones aprobadas."""
    with Session(get_engine()) as session:
        ticket = session.get(RfpTicket, ticket_id)
        if ticket is None or ticket.owner_id != str(current_user["id"]):
            raise HTTPException(status_code=404, detail="Ticket no encontrado.")
        if ticket.status != TERMINATED_STATUS or not ticket.final_document:
            raise HTTPException(status_code=409,
                                detail="El documento final aún no está disponible; "
                                       "faltan aprobaciones.")
        return {
            "ticket_id": str(ticket.ticket_id),
            "status": ticket.status,
            "document": ticket.final_document,
        }