from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from auth import get_current_user
import main
from main import app
from services.knowledge import pipeline


@pytest.fixture
def agent_client(tmp_path, monkeypatch) -> Iterator[TestClient]:
    monkeypatch.setenv("TRACKFLOW_AGENT_DATA_DIR", str(tmp_path / "agent-data"))
    monkeypatch.setattr(main, "init_inventory_db", lambda: None)
    monkeypatch.setattr(pipeline, "retrieve", lambda question: [{
        "company": "trackflow",
        "source_document": "returns-policy",
        "section": "Política de Devoluciones",
        "language": "es",
        "chunk_index": 0,
        "text": "Las devoluciones internacionales requieren gestión manual.",
    }])
    monkeypatch.setattr(
        pipeline,
        "generate_answer",
        lambda question, context: "Requieren gestión manual. [returns-policy]",
    )
    app.dependency_overrides[get_current_user] = lambda: {"id": "agent-user"}
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_agent_endpoint_saves_trace_and_restricts_it_to_its_owner(agent_client):
    response = agent_client.post(
        "/agent/query",
        json={"question": "¿Las devoluciones internacionales son automáticas?"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"] == "Requieren gestión manual. [returns-policy]"
    trace_id = payload["trace_id"]
    trace_response = agent_client.get(f"/agent/traces/{trace_id}")
    assert trace_response.status_code == 200
    trace = trace_response.json()
    assert trace["status"] == "completed"
    assert [event["node"] for event in trace["nodes"]] == [
        "receive", "retrieve", "generate",
    ]
    assert [event["order"] for event in trace["nodes"]] == [1, 2, 3]
    assert all(event["status"] == "completed" for event in trace["nodes"])
    assert trace["nodes"][0]["output"]["route"] == "retrieve"
    assert trace["nodes"][1]["output"]["route"] == "generate"
    assert trace["nodes"][1]["output"]["context"][0]["source_document"] == "returns-policy"
    assert trace["nodes"][2]["input"]["context"] == trace["nodes"][1]["output"]["context"]
    assert trace["answer"] == payload["answer"]

    app.dependency_overrides[get_current_user] = lambda: {"id": "other-user"}
    try:
        assert agent_client.get(f"/agent/traces/{trace_id}").status_code == 404
    finally:
        app.dependency_overrides[get_current_user] = lambda: {"id": "agent-user"}


def test_empty_question_is_rejected_and_traced_without_retrieval(
    agent_client, monkeypatch
):
    monkeypatch.setattr(pipeline, "retrieve", lambda question: pytest.fail("retrieve called"))
    monkeypatch.setattr(
        pipeline,
        "generate_answer",
        lambda question, context: pytest.fail("generate called"),
    )
    response = agent_client.post("/agent/query", json={"question": "   "})

    assert response.status_code == 422
    payload = response.json()
    trace = agent_client.get(f"/agent/traces/{payload['trace_id']}").json()
    assert trace["status"] == "rejected"
    assert [event["node"] for event in trace["nodes"]] == ["receive", "invalid_question"]
    assert trace["error_code"] == "invalid_question"


def test_failed_node_returns_sanitized_error_and_persists_failed_trace(
    agent_client, monkeypatch
):
    def fail_generation(question, context):
        raise RuntimeError("sensitive provider response")

    monkeypatch.setattr(pipeline, "generate_answer", fail_generation)
    response = agent_client.post(
        "/agent/query", json={"question": "¿Qué política aplica?"}
    )

    assert response.status_code == 503
    body = response.json()
    assert "sensitive provider response" not in response.text
    trace = agent_client.get(f"/agent/traces/{body['trace_id']}").json()
    assert trace["status"] == "failed"
    assert trace["error_code"] == "agent_error"
    assert [event["node"] for event in trace["nodes"]] == [
        "receive", "retrieve", "generate",
    ]
    assert trace["nodes"][-1]["status"] == "failed"
    assert trace["nodes"][-1]["error_code"] == "node_error"


def test_trace_endpoint_requires_authentication(tmp_path, monkeypatch):
    monkeypatch.setenv("TRACKFLOW_AGENT_DATA_DIR", str(tmp_path / "agent-data"))
    monkeypatch.setattr(main, "init_inventory_db", lambda: None)
    with TestClient(app) as client:
        response = client.get("/agent/traces/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 401
