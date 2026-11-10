import io
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine

from auth import get_current_user
from database import get_engine
from main import app
from models import RfpTicket
from services.rfp_tasks import process_rfp_task


@pytest.fixture
def rfp_client(tmp_path, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr("routes.rfp.get_engine", lambda: engine)
    monkeypatch.setattr("services.rfp_tasks.get_engine", lambda: engine)
    monkeypatch.setattr("routes.rfp.RAW_RFP_DIR", tmp_path / "raw")
    monkeypatch.setattr("services.rfp_tasks.RAW_RFP_DIR", tmp_path / "raw")
    monkeypatch.setattr("main.init_inventory_db", lambda: None)
    app.dependency_overrides[get_current_user] = lambda: {"id": 42}
    client = TestClient(app, raise_server_exceptions=False)
    yield client, engine, tmp_path
    client.close()
    app.dependency_overrides.clear()
    engine.dispose()


def test_upload_persists_pdf_enqueues_ticket_identifier_and_polling(rfp_client, monkeypatch):
    client, engine, tmp_path = rfp_client
    published = []
    import routes.rfp as rfp_route
    monkeypatch.setattr(rfp_route, "enqueue_rfp", lambda ticket_id: published.append({"args": [ticket_id], "task_id": ticket_id}))
    response = client.post("/api/rfps", files={"file": ("request.pdf", b"%PDF-test", "application/pdf")})
    assert response.status_code == 202, response.text
    payload = response.json()
    assert payload["status"] == "analizando"
    assert published == [{"args": [payload["ticket_id"]], "task_id": payload["ticket_id"]}]
    with Session(engine) as session:
        ticket = session.get(RfpTicket, UUID(payload["ticket_id"]))
        assert ticket is not None and ticket.owner_id == "42"
        assert open(ticket.raw_pdf_path, "rb").read() == b"%PDF-test"
    assert client.get(f"/api/rfps/{payload['ticket_id']}").json()["status"] == "analizando"


def test_pdf_validation_and_owner_isolation(rfp_client, monkeypatch):
    client, _, _ = rfp_client
    import routes.rfp as rfp_route
    monkeypatch.setattr(rfp_route, "enqueue_rfp", lambda _ticket_id: None)
    assert client.post("/api/rfps", files={"file": ("notes.txt", b"text", "text/plain")}).status_code == 400
    created = client.post("/api/rfps", files={"file": ("request.pdf", b"pdf", "application/pdf")}).json()
    app.dependency_overrides[get_current_user] = lambda: {"id": 12}
    assert client.get(f"/api/rfps/{created['ticket_id']}").status_code == 404


def test_worker_persists_metadata_workstreams_and_handoff(rfp_client, monkeypatch):
    client, engine, _ = rfp_client
    import routes.rfp as rfp_route
    import services.rfp_tasks as rfp_tasks

    monkeypatch.setattr(rfp_route, "enqueue_rfp", lambda _ticket_id: None)
    response = client.post("/api/rfps", files={"file": ("request.pdf", b"pdf", "application/pdf")})
    ticket_id = response.json()["ticket_id"]
    monkeypatch.setattr(rfp_tasks, "convert_pdf_to_markdown", lambda _pdf, markdown: "converted markdown")
    monkeypatch.setattr(rfp_tasks, "process_rfp_markdown", lambda _markdown, markdown_path: {
        "accepted": True,
        "reason": "customer_request_with_logistics_scope",
        "markdown_path": str(markdown_path),
        "metadata": {
            "client_name": "ModaViva", "client_country": "Spain", "services_requested": ["warehouse", "reverse"],
            "unknown_services": [], "monthly_volume": None, "monthly_volume_unit": None, "deadline": None,
            "budget_range": None, "departments_needed": ["warehouse", "reverse"], "currency": "EUR",
            "readability_metrics": {"word_count": 30, "readable": True},
        },
        "department_sections": [{"department_id": "warehouse", "approver": "Ana Whitfield", "key_aspects": ["storage"],
                                 "open_questions": ["volume?"], "source_extract": "storage"}],
        "handoff": {"ticket_id": None, "metadata": {}, "department_workstreams": [], "contract_version": "1.0"},
    })
    result = process_rfp_task.apply(args=[ticket_id], task_id=ticket_id)
    assert result.successful(), str(result.result)
    polled = client.get(f"/api/rfps/{ticket_id}").json()
    assert polled["status"] == "analisis_completo"
    assert polled["metadata"]["currency"] == "EUR"
    assert [section["department_id"] for section in polled["department_sections"]] == ["warehouse"]
    assert polled["handoff"]["ticket_id"] == ticket_id
