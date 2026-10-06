from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Uuid
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from models import TelemetryEventRecord
from routes.telemetry import router
from telemetry import normalized_route
from telemetry import TelemetryMiddleware

app = FastAPI()
app.include_router(router)
client = TestClient(app)


@pytest.fixture(autouse=True)
def telemetry_database(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TelemetryEventRecord.__table__.create(engine)

    import telemetry
    monkeypatch.setattr(telemetry, "get_engine", lambda: engine)
    yield engine
    engine.dispose()


def stored_events(engine):
    with Session(engine) as session:
        return session.exec(select(TelemetryEventRecord)).all()


def test_storage_schema_has_required_indexes():
    indexes = {index.name: index for index in TelemetryEventRecord.__table__.indexes}

    assert set(TelemetryEventRecord.__table__.columns.keys()) == {
        "id", "timestamp", "service", "event_type", "level", "value", "message", "tags",
    }
    assert isinstance(TelemetryEventRecord.__table__.c.id.type, Uuid)
    assert TelemetryEventRecord.__table__.c.id.primary_key
    assert str(TelemetryEventRecord.__table__.c.id.server_default.arg) == "gen_random_uuid()"
    assert TelemetryEventRecord.__table__.c.tags.server_default is not None
    assert "ix_telemetry_events_timestamp" in indexes
    assert "ix_telemetry_events_event_type" in indexes
    assert indexes["ix_telemetry_events_tags_gin"].dialect_options["postgresql"]["using"] == "gin"


def event():
    return {
        "eventId": str(uuid4()), "timestamp": "2026-10-03T12:00:00Z",
        "sessionId": str(uuid4()), "userId": None,
        "event_type": "backoffice_section_viewed", "schemaVersion": "1.0",
        "requestId": str(uuid4()), "properties": {"section": "inventory"},
    }


def test_valid_batch_uses_one_bulk_insert(telemetry_database, monkeypatch):
    original_execute = Session.execute
    bulk_calls = []

    def recording_execute(session, statement, *args, **kwargs):
        bulk_calls.append(statement)
        return original_execute(session, statement, *args, **kwargs)

    monkeypatch.setattr(Session, "execute", recording_execute)
    payload = [event(), event()]
    response = client.post("/telemetry/events", json={"events": payload})

    assert response.status_code == 200
    assert response.json() == {"received": 2, "stored": 2, "rejected": 0}
    assert len(bulk_calls) == 1
    records = stored_events(telemetry_database)
    assert len(records) == 2
    first_record = next(item for item in records if item.id == UUID(payload[0]["eventId"]))
    assert first_record.service == "backoffice"
    assert first_record.tags["section"] == "inventory"
    assert first_record.tags["requestId"] == payload[0]["requestId"]


def test_duplicate_event_ids_are_not_inserted_and_count_as_rejected(telemetry_database):
    payload = event()
    first = client.post("/telemetry/events", json={"events": [payload]})
    retry = client.post("/telemetry/events", json={"events": [payload, payload]})

    assert first.json() == {"received": 1, "stored": 1, "rejected": 0}
    assert retry.json() == {"received": 2, "stored": 0, "rejected": 2}
    assert len(stored_events(telemetry_database)) == 1


def test_backend_producer_maps_to_api_service(telemetry_database):
    payload = event() | {
        "event_type": "api_latency_recorded",
        "properties": {"method": "GET", "status_code": 200},
    }
    response = client.post("/telemetry/events", json={"events": [payload]})

    assert response.json() == {"received": 1, "stored": 1, "rejected": 0}
    assert stored_events(telemetry_database)[0].service == "api"


def test_business_dimensions_are_preserved_in_tags(telemetry_database):
    payload = event() | {
        "event_type": "inbound_order_created",
        "properties": {
            "order_id": 42,
            "sku": "sku-abc",
            "warehouse": "zaragoza",
            "quantity": 3,
        },
    }

    response = client.post("/telemetry/events", json={"events": [payload]})

    assert response.json() == {"received": 1, "stored": 1, "rejected": 0}
    record = stored_events(telemetry_database)[0]
    assert record.tags == {
        "order_id": 42,
        "sku": "SKU-ABC",
        "warehouse": "zaragoza",
        "quantity": 3,
        "sessionId": payload["sessionId"],
        "userId": None,
        "schemaVersion": "1.0",
        "requestId": payload["requestId"],
    }


def test_mixed_batch_persists_valid_events_and_counts_invalid(telemetry_database, monkeypatch):
    original_execute = Session.execute
    bulk_calls = []

    def recording_execute(session, statement, *args, **kwargs):
        bulk_calls.append(statement)
        return original_execute(session, statement, *args, **kwargs)

    monkeypatch.setattr(Session, "execute", recording_execute)
    response = client.post(
        "/telemetry/events",
        json={"events": [event(), event() | {"event_type": "unknown"}, 42]},
    )

    assert response.status_code == 200
    assert response.json() == {"received": 3, "stored": 1, "rejected": 2}
    assert len(bulk_calls) == 1
    assert len(stored_events(telemetry_database)) == 1


def test_fully_invalid_batch_is_accepted_without_database_write(telemetry_database, monkeypatch):
    def unexpected_add_all(*_args):
        pytest.fail("invalid events must not be inserted")

    monkeypatch.setattr(Session, "add_all", unexpected_add_all)
    response = client.post(
        "/telemetry/events",
        json={"events": [event() | {"timestamp": "invalid"}, None]},
    )

    assert response.status_code == 200
    assert response.json() == {"received": 2, "stored": 0, "rejected": 2}
    assert stored_events(telemetry_database) == []


def test_persistence_failure_rolls_back_batch(telemetry_database, monkeypatch):
    def fail_commit(_session):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(Session, "commit", fail_commit)
    response = client.post("/telemetry/events", json={"events": [event()]})

    assert response.status_code == 500
    assert response.json() == {"detail": "Telemetry persistence failed"}
    assert stored_events(telemetry_database) == []


def test_invalid_events_are_rejected_individually_and_invalid_envelopes_fail():
    for change in [{"email": "secret@example.com"}, {"properties": {"section": "inventory", "password": "secret"}}, {"properties": {"section": "unknown"}}, {"event_type": "unknown"}, {"timestamp": "2026-10-03T12:00:00"}]:
        payload = event() | change
        response = client.post("/telemetry/events", json={"events": [payload]})
        assert response.status_code == 200
        assert response.json() == {"received": 1, "stored": 0, "rejected": 1}
    assert client.post("/telemetry/events", json={"events": [], "extra": True}).status_code == 422
    assert client.post("/telemetry/events", json={"events": "invalid"}).status_code == 422
    assert client.post("/telemetry/events", json={"events": [event() | {"requestId": "synthetic-person-name"}]}).json() == {
        "received": 1, "stored": 0, "rejected": 1,
    }


def test_routes_remove_identifiers_queries_and_unknown_text():
    assert normalized_route("/inventory/products/123?email=secret") == "/inventory/products/{product_id}"
    assert normalized_route("/something/secret@example.com") == "/unknown"


def test_unhandled_exception_log_omits_message_and_raw_path(caplog):
    import asyncio
    from main import unhandled_exception_handler
    from starlette.requests import Request

    scope = {
        "type": "http", "method": "GET", "path": "/users/synthetic@example.test",
        "headers": [], "query_string": b"", "scheme": "http", "server": ("test", 80),
        "client": ("127.0.0.1", 1234), "http_version": "1.1",
    }
    with caplog.at_level("ERROR", logger="trackflow_api"):
        response = asyncio.run(unhandled_exception_handler(Request(scope), RuntimeError("synthetic@example.test")))
    assert response.status_code == 500
    assert "synthetic@example.test" not in caplog.text
    assert "/unknown" in caplog.text


def test_http_errors_latency_and_receiver_exclusion(monkeypatch):
    import telemetry

    captured = []
    monkeypatch.setattr(telemetry, "receive", lambda events: captured.extend(events))
    instrumented = FastAPI()
    instrumented.include_router(router)
    instrumented.add_middleware(TelemetryMiddleware)

    @instrumented.get("/health")
    def failure():
        raise RuntimeError("private failure body")

    @instrumented.get("/ok")
    def success():
        return {"status": "ok"}

    connection = TestClient(instrumented, raise_server_exceptions=False)
    response = connection.get("/health", headers={"X-Request-ID": "c84db3fb-f2a6-4d62-b8bc-3ba5bf70dcc8"})
    assert response.status_code == 500
    assert [item.event_type for item in captured] == ["api_latency_recorded", "api_error_recorded"]
    assert all(item.requestId == response.headers["x-request-id"] for item in captured)
    assert "private" not in str([item.model_dump() for item in captured])
    captured.clear()
    successful = connection.get("/ok")
    assert successful.status_code == 200
    assert [(item.event_type, item.properties["status_code"]) for item in captured] == [
        ("api_latency_recorded", 200)
    ]
    captured.clear()
    assert connection.post("/telemetry/events", json={"events": []}).status_code == 200
    assert captured == []


def test_auth_outcomes_and_expired_session(monkeypatch):
    import asyncio
    from datetime import timedelta
    import telemetry
    from auth import create_access_token, get_current_user, hash_password
    from auth_db import get_user_repository
    from auth_models import LoginInput, UserPersistence, utc_now_iso
    from routes.auth import login
    from fastapi import HTTPException
    import pytest

    captured = []
    monkeypatch.setattr(telemetry, "receive", lambda events: captured.extend(events))
    user = get_user_repository().create(UserPersistence(email="private@example.com", hashed_password=hash_password("password"), role="admin", is_active=True, created_at=utc_now_iso()))
    login(LoginInput(email="private@example.com", password="password"))
    with pytest.raises(HTTPException):
        login(LoginInput(email="private@example.com", password="incorrect"))
    expired = create_access_token({"sub": str(user.id)}, timedelta(minutes=-1))
    with pytest.raises(HTTPException):
        asyncio.run(get_current_user(expired))
    assert [item.event_type for item in captured] == ["login_succeeded", "login_failed", "session_expired"]
    assert captured[0].userId == str(user.id)
    assert captured[1].userId is None
    assert "private@example.com" not in str([item.model_dump() for item in captured])