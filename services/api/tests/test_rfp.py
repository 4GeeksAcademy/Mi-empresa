import io
import json
import asyncio
from datetime import datetime, timezone
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine, select

from auth import get_current_user
from database import get_engine
from main import app
from models import RfpMetadataRecord, RfpNodeTrace, RfpTicket
from services.rfp_approval_tasks import approval_snapshot
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


def test_rfp_sse_stream_uses_named_event_and_briefing_payload(rfp_client, monkeypatch):
    client, engine, _ = rfp_client
    import routes.rfp as rfp_route
    monkeypatch.setattr(rfp_route, "enqueue_rfp", lambda _ticket_id: None)
    created = client.post("/api/rfps", files={"file": ("request.pdf", b"pdf", "application/pdf")}).json()
    assert client.get("/api/rfps", params={"created_after": "2000-01-01T00:00:00Z"}).json() == []
    with Session(engine) as session:
        ticket = session.get(RfpTicket, UUID(created["ticket_id"]))
        ticket.classification_result = True
        ticket.accepted_at = datetime.now(timezone.utc)
        session.add(RfpMetadataRecord(
            ticket_id=ticket.ticket_id, client_name="Northline Apparel", client_country="US",
            services_requested=["warehouse", "lastmile"],
        ))
        session.commit()
    original_stream = rfp_route._rfp_event_stream

    async def one_event(owner_id: str, cursor: datetime):
        stream = original_stream(owner_id, cursor)
        try:
            yield await anext(stream)
        finally:
            await stream.aclose()

    monkeypatch.setattr(rfp_route, "_rfp_event_stream", one_event)
    with Session(engine) as session:
        persisted_ticket = session.get(RfpTicket, UUID(created["ticket_id"]))
        expected_created_at = persisted_ticket.accepted_at.isoformat()

    import routes.rfp as rfp_route
    response = rfp_route.stream_rfp_tickets(
        since=datetime.fromisoformat("2000-01-01T00:00:00+00:00"), current_user={"id": 42}
    )
    assert response.media_type == "text/event-stream"
    assert response.headers["cache-control"] == "no-cache, no-transform"
    first_chunk = asyncio.run(anext(response.body_iterator))
    asyncio.run(response.body_iterator.aclose())
    frame = first_chunk.decode() if isinstance(first_chunk, bytes) else first_chunk
    assert f"id: {created['ticket_id']}\nevent: rfp_ticket_created\ndata: " in frame
    data_line = next(line[6:] for line in frame.splitlines() if line.startswith("data: "))
    assert json.loads(data_line) == {
        "ticket_id": created["ticket_id"], "rfp_id": created["rfp_id"],
        "client_name": "Northline Apparel", "client_country": "US",
        "services_requested": ["warehouse", "lastmile"], "status": "analyzing",
        "created_at": expected_created_at,
    }
    assert "raw_pdf_path" not in data_line and "filename" not in data_line
    assert response.headers["content-type"].startswith("text/event-stream")


def test_rfp_snapshot_recovery_is_owner_scoped_and_filters_created_after(rfp_client, monkeypatch):
    client, engine, _ = rfp_client
    import routes.rfp as rfp_route
    monkeypatch.setattr(rfp_route, "enqueue_rfp", lambda _ticket_id: None)
    created = client.post("/api/rfps", files={"file": ("request.pdf", b"pdf", "application/pdf")}).json()
    with Session(engine) as session:
        ticket = session.get(RfpTicket, UUID(created["ticket_id"]))
        ticket.classification_result = True
        ticket.accepted_at = datetime.now(timezone.utc)
        session.commit()
    response = client.get("/api/rfps", params={"created_after": "2000-01-01T00:00:00Z"})
    assert response.status_code == 200
    assert [item["ticket_id"] for item in response.json()] == [created["ticket_id"]]
    assert response.json()[0]["accepted_at"] is not None
    accepted_at = response.json()[0]["accepted_at"]
    assert [item["ticket_id"] for item in client.get(
        "/api/rfps", params={"created_after": accepted_at}
    ).json()] == [created["ticket_id"]]
    assert client.get("/api/rfps", params={"created_after": "2999-01-01T00:00:00Z"}).json() == []

    app.dependency_overrides[get_current_user] = lambda: {"id": 7}
    assert client.get("/api/rfps", params={"created_after": "2000-01-01T00:00:00Z"}).json() == []


def test_rejected_document_is_not_recoverable_as_new_rfp(rfp_client, monkeypatch):
    client, engine, _ = rfp_client
    import routes.rfp as rfp_route
    import services.rfp_tasks as rfp_tasks

    monkeypatch.setattr(rfp_route, "enqueue_rfp", lambda _ticket_id: None)
    created = client.post("/api/rfps", files={"file": ("pitch.pdf", b"pdf", "application/pdf")}).json()
    monkeypatch.setattr(rfp_tasks, "convert_pdf_to_markdown", lambda _pdf, markdown: "carrier sales presentation")
    monkeypatch.setattr(rfp_tasks, "classify_document", lambda _markdown: (False, "carrier_pitch"))
    monkeypatch.setattr(rfp_tasks, "process_rfp_markdown", lambda _markdown, _path, **_kwargs: pytest.fail(
        "Rejected documents must not continue into graph processing"
    ))
    result = process_rfp_task.apply(args=[created["ticket_id"]], task_id=created["ticket_id"])
    assert result.successful(), str(result.result)
    with Session(engine) as session:
        ticket = session.get(RfpTicket, UUID(created["ticket_id"]))
        assert ticket.classification_result is False
        assert ticket.accepted_at is None
    assert client.get("/api/rfps", params={"created_after": "2000-01-01T00:00:00Z"}).json() == []


def test_accepted_ticket_is_persisted_before_graph_processing(rfp_client, monkeypatch):
    client, engine, _ = rfp_client
    import routes.rfp as rfp_route
    import services.rfp_tasks as rfp_tasks

    monkeypatch.setattr(rfp_route, "enqueue_rfp", lambda _ticket_id: None)
    created = client.post("/api/rfps", files={"file": ("request.pdf", b"pdf", "application/pdf")}).json()
    monkeypatch.setattr(rfp_tasks, "convert_pdf_to_markdown", lambda _pdf, markdown: "customer needs warehousing logistics")
    monkeypatch.setattr(rfp_tasks, "classify_document", lambda _markdown: (True, "customer_request"))
    metadata = {
        "client_name": "Northline Apparel", "client_country": "US", "services_requested": ["warehouse"],
        "unknown_services": [], "monthly_volume": None, "monthly_volume_unit": None, "deadline": None,
        "budget_range": None, "departments_needed": ["warehouse"], "currency": "USD",
    }
    monkeypatch.setattr(rfp_tasks, "extract_metadata", lambda _markdown: metadata.copy())
    monkeypatch.setattr(rfp_tasks, "readability_metrics", lambda _markdown: {"word_count": 12, "readable": True})

    def finish_graph(_markdown, _path, **kwargs):
        with Session(engine) as session:
            ticket = session.get(RfpTicket, UUID(created["ticket_id"]))
            assert ticket.classification_result is True
            assert ticket.accepted_at is not None
            assert session.get(RfpMetadataRecord, ticket.ticket_id) is not None
        assert kwargs["accepted"] is True
        assert kwargs["metadata"]["client_name"] == "Northline Apparel"
        return {"accepted": True, "reason": "customer_request", "markdown_path": "request.md",
                "metadata": metadata, "department_sections": [],
                "handoff": {"ticket_id": None, "metadata": {}, "department_workstreams": [], "contract_version": "1.0"}}

    monkeypatch.setattr(rfp_tasks, "process_rfp_markdown", finish_graph)
    result = process_rfp_task.apply(args=[created["ticket_id"]], task_id=created["ticket_id"])
    assert result.successful(), str(result.result)


def test_rfp_sse_requires_authentication(rfp_client):
    client, _, _ = rfp_client
    app.dependency_overrides.clear()
    assert client.get("/api/rfps/events").status_code == 401


def test_migration_runner_includes_sse_acceptance_migration():
    from apply_rfp_approval_migration import MIGRATIONS

    assert "20261112_rfp_sse_acceptance.sql" in MIGRATIONS
    assert MIGRATIONS.index("20261024_rfp_intake.sql") < MIGRATIONS.index("20261112_rfp_sse_acceptance.sql")
    assert MIGRATIONS.index("20261110_rfp_response_generation.sql") < MIGRATIONS.index("20261112_rfp_sse_acceptance.sql")


def test_worker_persists_metadata_workstreams_and_handoff(rfp_client, monkeypatch):
    client, engine, _ = rfp_client
    import routes.rfp as rfp_route
    import services.rfp_tasks as rfp_tasks

    monkeypatch.setattr(rfp_route, "enqueue_rfp", lambda _ticket_id: None)
    response = client.post("/api/rfps", files={"file": ("request.pdf", b"pdf", "application/pdf")})
    ticket_id = response.json()["ticket_id"]
    monkeypatch.setattr(rfp_tasks, "convert_pdf_to_markdown", lambda _pdf, markdown: "converted markdown")
    monkeypatch.setattr(rfp_tasks, "classify_document", lambda _markdown: (True, "customer_request_with_logistics_scope"))
    monkeypatch.setattr(rfp_tasks, "extract_metadata", lambda _markdown: {
        "client_name": "ModaViva", "client_country": "Spain", "services_requested": ["warehouse", "reverse"],
        "unknown_services": [], "monthly_volume": None, "monthly_volume_unit": None, "deadline": None,
        "budget_range": None, "departments_needed": ["warehouse", "reverse"], "currency": "EUR",
    })
    monkeypatch.setattr(rfp_tasks, "readability_metrics", lambda _markdown: {"word_count": 30, "readable": True})
    monkeypatch.setattr(rfp_tasks, "process_rfp_markdown", lambda _markdown, markdown_path, **_kwargs: {
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
    assert polled["accepted_at"] is not None
    assert polled["metadata"]["currency"] == "EUR"
    assert [section["department_id"] for section in polled["department_sections"]] == ["warehouse"]
    assert polled["handoff"]["ticket_id"] == ticket_id


def test_response_endpoints_enqueue_and_persist_handoff(rfp_client, monkeypatch):
    client, engine, _ = rfp_client
    import routes.rfp as rfp_route
    import services.rfp_tasks as rfp_tasks

    monkeypatch.setattr(rfp_route, "enqueue_rfp", lambda _ticket_id: None)
    created = client.post("/api/rfps", files={"file": ("request.pdf", b"pdf",
                                                        "application/pdf")}).json()
    ticket_id = created["ticket_id"]

    # 409 mientras no esté analisis_completo
    assert client.post(f"/api/rfps/{ticket_id}/response").status_code == 409

    # ticket en analisis_completo pero SIN synthesizer_payload -> 409
    with Session(engine) as session:
        ticket = session.get(RfpTicket, UUID(ticket_id))
        ticket.status = "analisis_completo"
        session.add(ticket)
        session.commit()
    assert client.post(f"/api/rfps/{ticket_id}/response").status_code == 409

    published = []
    monkeypatch.setattr(
        rfp_route, "enqueue_response",
        lambda tid: published.append({"args": [tid],
                                      "task_id": f"{tid}-response"}),
    )
    with Session(engine) as session:
        ticket = session.get(RfpTicket, UUID(ticket_id))
        ticket.synthesizer_payload = {"handoff": {"ticket_id": ticket_id}}
        session.add(ticket)
        session.commit()

    response = client.post(f"/api/rfps/{ticket_id}/response")
    assert response.status_code == 202, response.text
    assert response.json() == {"ticket_id": ticket_id,
                               "status": "generando_borrador"}
    assert published == [{"args": [ticket_id], "task_id": f"{ticket_id}-response"}]
    with Session(engine) as session:
        ticket = session.get(RfpTicket, UUID(ticket_id))
        assert ticket.status == "generando_borrador"


def test_response_enqueue_failure_restores_retryable_ticket_state(rfp_client, monkeypatch):
    client, engine, _ = rfp_client
    import routes.rfp as rfp_route

    monkeypatch.setattr(rfp_route, "enqueue_rfp", lambda _tid: None)
    created = client.post("/api/rfps", files={"file": ("request.pdf", b"pdf",
                                                        "application/pdf")}).json()
    ticket_id = created["ticket_id"]
    with Session(engine) as session:
        ticket = session.get(RfpTicket, UUID(ticket_id))
        ticket.status = "analisis_completo"
        ticket.synthesizer_payload = {"handoff": {"ticket_id": ticket_id}}
        session.add(ticket)
        session.commit()

    def fail_enqueue(_ticket_id):
        raise RuntimeError("broker unavailable")

    monkeypatch.setattr(rfp_route, "enqueue_response", fail_enqueue)
    response = client.post(f"/api/rfps/{ticket_id}/response")

    assert response.status_code == 503
    with Session(engine) as session:
        ticket = session.get(RfpTicket, UUID(ticket_id))
        assert ticket.status == "analisis_completo"


def test_get_response_returns_persisted_sections_and_handoff(rfp_client, monkeypatch):
    client, engine, _ = rfp_client
    import routes.rfp as rfp_route

    monkeypatch.setattr(rfp_route, "enqueue_rfp", lambda _tid: None)
    monkeypatch.setattr(rfp_route, "enqueue_response", lambda _tid: None)
    created = client.post("/api/rfps", files={"file": ("request.pdf", b"pdf",
                                                        "application/pdf")}).json()
    ticket_id = created["ticket_id"]
    with Session(engine) as session:
        ticket = session.get(RfpTicket, UUID(ticket_id))
        ticket.status = "en_evaluación"
        ticket.synthesizer_payload = {"handoff": {"ticket_id": ticket_id}}
        ticket.response_handoff = {"ticket_id": ticket_id,
                                   "contract_version": "2.0"}
        session.add(ticket)
        session.commit()

    polled = client.get(f"/api/rfps/{ticket_id}/response").json()
    assert polled["ticket_id"] == ticket_id
    assert polled["status"] == "en_evaluación"
    assert polled["handoff"]["contract_version"] == "2.0"
    assert polled["sections"] == []
    # dueño distinto -> 404
    app.dependency_overrides[get_current_user] = lambda: {"id": 7}
    assert client.get(f"/api/rfps/{ticket_id}/response").status_code == 404


def test_start_approvals_persists_waiting_status_and_enqueues(rfp_client, monkeypatch):
    client, engine, _ = rfp_client
    import routes.rfp as rfp_route

    monkeypatch.setattr(rfp_route, "enqueue_rfp", lambda _tid: None)
    created = client.post("/api/rfps", files={"file": ("request.pdf", b"pdf",
                                                        "application/pdf")}).json()
    ticket_id = created["ticket_id"]
    with Session(engine) as session:
        ticket = session.get(RfpTicket, UUID(ticket_id))
        ticket.status = "needs_human_review"
        ticket.classification_result = True
        ticket.response_handoff = {"ticket_id": ticket_id, "sections": [
            {"department_id": "warehouse", "draft_content": "Draft"},
        ]}
        session.add(ticket)
        session.commit()

    published = []
    monkeypatch.setattr(rfp_route, "enqueue_approvals",
                        lambda tid: published.append(tid))
    response = client.post(f"/api/rfps/{ticket_id}/approvals")
    assert response.status_code == 202, response.text
    assert response.json() == {"ticket_id": ticket_id,
                               "status": "esperando_aprobación"}
    assert published == [ticket_id]
    with Session(engine) as session:
        assert session.get(RfpTicket, UUID(ticket_id)).status == "esperando_aprobación"
    # A repeated start is rejected rather than scheduling a second run.
    assert client.post(f"/api/rfps/{ticket_id}/approvals").status_code == 409


def test_start_approvals_restores_status_if_enqueue_fails(rfp_client, monkeypatch):
    client, engine, _ = rfp_client
    import routes.rfp as rfp_route

    monkeypatch.setattr(rfp_route, "enqueue_rfp", lambda _tid: None)
    created = client.post("/api/rfps", files={"file": ("request.pdf", b"pdf",
                                                        "application/pdf")}).json()
    ticket_id = created["ticket_id"]
    with Session(engine) as session:
        ticket = session.get(RfpTicket, UUID(ticket_id))
        ticket.status = "needs_human_review"
        ticket.classification_result = True
        ticket.response_handoff = {"ticket_id": ticket_id, "sections": [
            {"department_id": "warehouse", "draft_content": "Draft"},
        ]}
        session.add(ticket)
        session.commit()

    def fail_enqueue(_ticket_id):
        raise RuntimeError("broker unavailable")

    monkeypatch.setattr(rfp_route, "enqueue_approvals", fail_enqueue)
    response = client.post(f"/api/rfps/{ticket_id}/approvals")
    assert response.status_code == 503
    with Session(engine) as session:
        assert session.get(RfpTicket, UUID(ticket_id)).status == "needs_human_review"


def test_approval_decision_requires_valid_responsible_and_interrupt(rfp_client,
                                                                    monkeypatch):
    client, engine, _ = rfp_client
    import routes.rfp as rfp_route

    monkeypatch.setattr(rfp_route, "enqueue_rfp", lambda _tid: None)
    created = client.post("/api/rfps", files={"file": ("request.pdf", b"pdf",
                                                        "application/pdf")}).json()
    ticket_id = created["ticket_id"]
    with Session(engine) as session:
        ticket = session.get(RfpTicket, UUID(ticket_id))
        ticket.status = "esperando_aprobación"
        ticket.classification_result = True
        ticket.response_handoff = {"ticket_id": ticket_id, "sections": []}
        session.add(ticket)
        session.commit()

    enqueued = []
    monkeypatch.setattr(rfp_route, "enqueue_decision",
                        lambda tid, dept, payload: enqueued.append((tid, dept, payload)))
    base = {"decision": "aprobar", "approver": "Ana Whitfield",
            "comment": "", "interrupt_id": "interrupt-1"}
    invalid_approver = {**base, "approver": "Carlos Vega"}
    assert client.post(f"/api/rfps/{ticket_id}/approvals/warehouse",
                       json=invalid_approver).status_code == 400
    assert client.post(f"/api/rfps/{ticket_id}/approvals/warehouse",
                       json={**base, "interrupt_id": ""}).status_code == 400

    response = client.post(f"/api/rfps/{ticket_id}/approvals/warehouse", json=base)
    assert response.status_code == 200, response.text
    assert response.json()["decision"] == "aprobar"
    assert enqueued == [(ticket_id, "warehouse", base)]


def test_approval_snapshot_and_final_document_are_owner_scoped(rfp_client,
                                                                monkeypatch):
    client, engine, _ = rfp_client
    import routes.rfp as rfp_route

    monkeypatch.setattr(rfp_route, "enqueue_rfp", lambda _tid: None)
    created = client.post("/api/rfps", files={"file": ("request.pdf", b"pdf",
                                                        "application/pdf")}).json()
    ticket_id = created["ticket_id"]
    monkeypatch.setattr(rfp_route, "approval_snapshot", lambda _ticket: {
        "ticket_id": ticket_id, "status": "esperando_aprobación",
        "pending": ["warehouse"],
    })
    snapshot = client.get(f"/api/rfps/{ticket_id}/approvals")
    assert snapshot.status_code == 200
    assert snapshot.json()["pending"] == ["warehouse"]
    assert client.get(f"/api/rfps/{ticket_id}/final-document").status_code == 409

    with Session(engine) as session:
        ticket = session.get(RfpTicket, UUID(ticket_id))
        ticket.status = "terminado"
        ticket.final_document = {"currency": "EUR", "content": "Final"}
        session.add(ticket)
        session.commit()
    result = client.get(f"/api/rfps/{ticket_id}/final-document")
    assert result.status_code == 200
    assert result.json()["document"]["content"] == "Final"

    app.dependency_overrides[get_current_user] = lambda: {"id": 99}
    assert client.get(f"/api/rfps/{ticket_id}/approvals").status_code == 404
    assert client.get(f"/api/rfps/{ticket_id}/final-document").status_code == 404


def test_approval_trace_sink_commits_trace_to_database(rfp_client, monkeypatch):
    client, engine, _ = rfp_client
    import routes.rfp as rfp_route
    import services.rfp_approval_tasks as approval_tasks

    monkeypatch.setattr(rfp_route, "enqueue_rfp", lambda _ticket_id: None)
    monkeypatch.setattr(approval_tasks, "get_engine", lambda: engine)
    created = client.post("/api/rfps", files={
        "file": ("request.pdf", b"pdf", "application/pdf"),
    }).json()
    ticket_id = UUID(created["ticket_id"])

    approval_tasks._trace_sink(str(ticket_id), {
        "node": "human_decision",
        "agent": "human_decision",
        "department": "warehouse",
        "input": {"interrupt_id": "pending-1"},
        "output": {"decision": "aprobar"},
        "timestamp": "2026-12-01T00:00:00+00:00",
    })

    with Session(engine) as session:
        traces = session.exec(select(RfpNodeTrace).where(
            RfpNodeTrace.ticket_id == ticket_id)).all()
    assert len(traces) == 1
    assert traces[0].node == "human_decision"
    assert traces[0].department == "warehouse"
    assert traces[0].input == {"interrupt_id": "pending-1"}
    assert traces[0].output == {"decision": "aprobar"}


def test_approval_trace_sink_propagates_persistence_failure(
        rfp_client, monkeypatch):
    _, engine, _ = rfp_client
    import services.rfp_approval_tasks as approval_tasks

    monkeypatch.setattr(approval_tasks, "get_engine", lambda: engine)
    monkeypatch.setattr(approval_tasks, "Session", lambda _engine: BrokenSession())

    class BrokenSession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def add(self, _record):
            pass

        def commit(self):
            raise RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        approval_tasks._trace_sink("00000000-0000-0000-0000-000000000001", {
            "node": "human_decision", "agent": "human_decision",
            "department": "warehouse", "input": {}, "output": {},
        })


def test_approval_task_retries_when_trace_persistence_fails(
        rfp_client, monkeypatch):
    client, engine, tmp_path = rfp_client
    import routes.rfp as rfp_route
    import services.rfp_approval_tasks as approval_tasks

    monkeypatch.setattr(rfp_route, "enqueue_rfp", lambda _ticket_id: None)
    monkeypatch.setattr(approval_tasks, "get_engine", lambda: engine)
    monkeypatch.setattr(approval_tasks, "approval_checkpoint_db",
                        lambda: tmp_path / "approval.db")
    created = client.post("/api/rfps", files={
        "file": ("request.pdf", b"pdf", "application/pdf"),
    }).json()
    ticket_id = created["ticket_id"]

    with Session(engine) as session:
        ticket = session.get(RfpTicket, UUID(ticket_id))
        ticket.classification_result = True
        ticket.response_handoff = {
            "ticket_id": ticket_id,
            "metadata": {"client_name": "ModaViva", "client_country": "Spain",
                         "currency": "EUR", "departments_needed": ["warehouse"]},
            "sections": [{
                "department_id": "warehouse",
                "approver": "Ana Whitfield",
                "draft_content": "## Warehouse Operations — ModaViva\nTodo en EUR.",
                "evaluation_results": {
                    "overall_pass": True, "compliance": {"violations": []}},
            }],
            "department_workstreams": [{
                "department_id": "warehouse", "approver": "Ana Whitfield",
                "open_questions": [],
            }],
        }
        session.add(ticket)
        session.commit()

    monkeypatch.setattr(
        approval_tasks, "_trace_sink",
        lambda _ticket_id, _entry: (_ for _ in ()).throw(
            RuntimeError("trace database unavailable")))

    countdowns = []
    original_retry = approval_tasks.start_rfp_approvals_task.retry

    def retry(*, exc, countdown):
        countdowns.append(countdown)
        return original_retry(exc=exc, countdown=countdown)

    monkeypatch.setattr(approval_tasks.start_rfp_approvals_task, "retry", retry)
    result = approval_tasks.start_rfp_approvals_task.apply(args=[ticket_id])

    assert result.failed()
    # Celery invoca retry también en el intento final; max_retries=2 produce
    # dos reintentos después del intento inicial (tres llamadas a retry).
    assert countdowns == [30, 30, 30]
    assert "trace database unavailable" in str(result.result)


def test_api_approval_flow_runs_tasks_and_persists_final_document(
        rfp_client, monkeypatch):
    client, engine, tmp_path = rfp_client
    import routes.rfp as rfp_route
    import services.rfp_approval_tasks as approval_tasks

    monkeypatch.setattr(rfp_route, "enqueue_rfp", lambda _ticket_id: None)
    ticket_response = client.post("/api/rfps", files={
        "file": ("request.pdf", b"pdf", "application/pdf"),
    })
    assert ticket_response.status_code == 202, ticket_response.text
    ticket_id = UUID(ticket_response.json()["ticket_id"])
    checkpoint = tmp_path / "approval.db"

    monkeypatch.setattr(rfp_route, "enqueue_approvals",
                        lambda _ticket_id: approval_tasks.start_rfp_approvals_task.run(
                            _ticket_id))
    monkeypatch.setattr(rfp_route, "enqueue_decision",
                        lambda tid, dept, payload:
                        approval_tasks.record_rfp_decision_task.run(
                            tid, dept, payload))
    monkeypatch.setattr(approval_tasks, "approval_checkpoint_db",
                        lambda: checkpoint)
    monkeypatch.setattr(approval_tasks, "get_engine", lambda: engine)

    with Session(engine) as session:
        ticket = session.get(RfpTicket, ticket_id)
        ticket.classification_result = True
        ticket.status = "needs_human_review"
        ticket.response_handoff = {
            "ticket_id": str(ticket_id),
            "metadata": {"client_name": "ModaViva", "client_country": "Spain",
                         "currency": "EUR", "departments_needed": ["warehouse"]},
            "sections": [{
                "department_id": "warehouse",
                "approver": "Ana Whitfield",
                "draft_content": "## Warehouse Operations — ModaViva\nTodo en EUR.",
                "evaluation_results": {"overall_pass": True, "compliance": {"violations": []}},
            }],
            "department_workstreams": [{
                "department_id": "warehouse", "approver": "Ana Whitfield",
                "open_questions": [],
            }],
        }
        session.add(ticket)
        session.commit()

    started = client.post(f"/api/rfps/{ticket_id}/approvals")
    assert started.status_code == 202, started.text
    snapshot = client.get(f"/api/rfps/{ticket_id}/approvals")
    assert snapshot.status_code == 200, snapshot.text
    interrupt_id = snapshot.json()["departments"][0]["interrupt_id"]
    assert interrupt_id

    decision = client.post(
        f"/api/rfps/{ticket_id}/approvals/warehouse",
        json={"decision": "aprobar", "approver": "Ana Whitfield",
              "comment": "Conforme.", "interrupt_id": interrupt_id})
    assert decision.status_code == 200, decision.text
    final = client.get(f"/api/rfps/{ticket_id}/final-document")
    assert final.status_code == 200, final.text
    assert final.json()["document"]["currency"] == "EUR"

    with Session(engine) as session:
        stored_ticket = session.get(RfpTicket, ticket_id)
        traces = session.exec(select(RfpNodeTrace).where(
            RfpNodeTrace.ticket_id == ticket_id)).all()
    assert stored_ticket.status == "terminado"
    assert stored_ticket.final_document == final.json()["document"]
    assert {trace.node for trace in traces} >= {
        "start_approvals", "human_decision", "coordinator"}
