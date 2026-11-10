from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from celery import shared_task
from sqlmodel import Session, select

from database import get_engine
from data.pipelines.rfp_intake.pipeline import convert_pdf_to_markdown
from services.rfp_graph import process_rfp_markdown
from models import DepartmentSectionRecord, RfpMetadataRecord, RfpTicket

logger = logging.getLogger("trackflow_rfp")
RAW_RFP_DIR = Path(os.environ.get("RFP_RAW_DIR", "/app/data/raw/rfps"))


@shared_task(bind=True, name="services.rfp_tasks.process_rfp_task", max_retries=2, acks_late=True)
def process_rfp_task(self, ticket_id: str) -> dict:
    identifier = UUID(ticket_id)
    try:
        with Session(get_engine()) as session:
            ticket = session.get(RfpTicket, identifier)
            if ticket is None:
                raise ValueError("RFP ticket not found")
            if ticket.status in {"analisis_completo", "descartado"}:
                return {"ticket_id": ticket_id, "status": ticket.status}
            raw_path = Path(ticket.raw_pdf_path)
            markdown_path = RAW_RFP_DIR / str(ticket.owner_id) / f"{identifier}.md"
            markdown = convert_pdf_to_markdown(raw_path, markdown_path)
            result = process_rfp_markdown(markdown, str(markdown_path))
            ticket.markdown_path = str(markdown_path)
            ticket.classification_result = result["accepted"]
            ticket.classification_reason = result["reason"]
            ticket.updated_at = datetime.now(timezone.utc)
            ticket.processing_error = None
            if not result["accepted"]:
                ticket.status = "descartado"
            else:
                metadata = result["metadata"]
                metadata_record = RfpMetadataRecord(ticket_id=identifier, **metadata)
                existing = session.get(RfpMetadataRecord, identifier)
                if existing:
                    for key, value in metadata.items():
                        setattr(existing, key, value)
                    session.add(existing)
                else:
                    session.add(metadata_record)
                for section_data in result["department_sections"]:
                    existing_section = session.exec(select(DepartmentSectionRecord).where(
                        DepartmentSectionRecord.ticket_id == identifier,
                        DepartmentSectionRecord.department_id == section_data["department_id"],
                    )).first()
                    if existing_section:
                        for key, value in section_data.items():
                            setattr(existing_section, key, value)
                        session.add(existing_section)
                    else:
                        session.add(DepartmentSectionRecord(ticket_id=identifier, **section_data))
                handoff = result["handoff"]
                handoff["ticket_id"] = ticket_id
                ticket.synthesizer_payload = handoff
                ticket.status = "analisis_completo"
            session.add(ticket)
            session.commit()
            return {"ticket_id": ticket_id, "status": ticket.status}
    except Exception as exc:
        logger.exception("RFP processing failed ticket_id=%s error_type=%s", ticket_id, type(exc).__name__)
        try:
            with Session(get_engine()) as session:
                ticket = session.get(RfpTicket, identifier)
                if ticket:
                    ticket.processing_error = f"Processing failed ({type(exc).__name__})"
                    ticket.updated_at = datetime.now(timezone.utc)
                    session.add(ticket)
                    session.commit()
        except Exception:
            logger.exception("Could not persist RFP processing failure ticket_id=%s", ticket_id)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=2 ** self.request.retries)
        raise