from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlmodel import Session, select

from auth import get_current_user
from database import get_engine
from models import DepartmentSectionRecord, RfpMetadataRecord, RfpTicket
from services.rfp_tasks import process_rfp_task
from services.response_tasks import generate_rfp_response_task

router = APIRouter(prefix="/api/rfps", tags=["rfps"])
MAX_PDF_BYTES = 25 * 1024 * 1024
RAW_RFP_DIR = Path(os.environ.get("RFP_RAW_DIR", "/app/data/raw/rfps"))


def enqueue_rfp(ticket_id: str) -> None:
    process_rfp_task.apply_async(args=[ticket_id], task_id=ticket_id)


def enqueue_response(ticket_id: str) -> None:
    """Parte 2: el router solo despacha; la lógica vive en el pipeline."""
    generate_rfp_response_task.apply_async(args=[ticket_id],
                                           task_id=f"{ticket_id}-response")


def _ticket_response(ticket: RfpTicket, metadata: RfpMetadataRecord | None, sections: list[DepartmentSectionRecord]) -> dict:
    return {
        "ticket_id": str(ticket.ticket_id),
        "rfp_id": str(ticket.rfp_id),
        "status": ticket.status,
        "filename": ticket.original_filename,
        "created_at": ticket.created_at.isoformat(),
        "classification": {"is_rfp": ticket.classification_result, "reason": ticket.classification_reason},
        "processing_error": ticket.processing_error,
        "metadata": metadata.model_dump(mode="json") if metadata else None,
        "department_sections": [section.model_dump(mode="json") for section in sections],
        "handoff": ticket.synthesizer_payload,
    }


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