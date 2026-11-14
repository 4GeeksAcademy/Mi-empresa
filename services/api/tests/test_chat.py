from __future__ import annotations

import asyncio
import time
from pathlib import Path
from threading import Event

import pytest
from fastapi.testclient import TestClient

import main
from auth import create_access_token, get_current_user
from auth_db import get_user_repository
from auth_models import UserPersistence, utc_now_iso
from services.support_agent.chat import ChatHub
from services.support_agent.memory import AgentMemoryStore
from services.support_agent.traces import AgentTraceStore
from services.knowledge import pipeline


@pytest.fixture
def chat_client(tmp_path, monkeypatch):
    monkeypatch.setenv("TRACKFLOW_AGENT_DATA_DIR", str(tmp_path / "agent-data"))
    monkeypatch.setattr(main, "init_inventory_db", lambda: None)
    monkeypatch.setattr(pipeline, "retrieve", lambda question: [{
        "company": "trackflow", "source_document": "returns-policy",
        "section": "returns", "language": "es", "chunk_index": 0,
        "text": "Las devoluciones requieren gestión manual.",
    }])
    monkeypatch.setattr("auth.SECRET_KEY", "test-secret-key-for-auth-088")
    user = get_user_repository().create(UserPersistence(
        email="chat@trackflow.com", hashed_password="test-hash", role="user",
        is_active=True, created_at=utc_now_iso(),
    ))
    app = main.app
    app.dependency_overrides[get_current_user] = lambda: {"id": user.id, "client_id": "brand-7"}
    try:
        with TestClient(app) as client:
            yield client, user.id
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_chat_requires_jwt_before_accept(chat_client):
    client, _user_id = chat_client
    with pytest.raises(Exception):
        with client.websocket_connect("/agent/chat/00000000-0000-0000-0000-000000000001"):
            pass


def test_chat_streams_contract_and_rehydrates_same_session(chat_client, monkeypatch):
    from services.knowledge import pipeline
    client, user_id = chat_client

    def fake_generate(question, context):
        sink = pipeline._generation_sink.get()
        if sink:
            on_token, cancelled, _register_abort = sink
            for piece in ("Respuesta ", "en vivo"):
                if cancelled.is_set():
                    break
                on_token(piece)
                time.sleep(0.01)
        return "Respuesta en vivo"

    monkeypatch.setattr(pipeline, "generate_answer", fake_generate)
    session_id = "00000000-0000-0000-0000-000000000002"
    token = create_access_token({"sub": str(user_id)})
    with client.websocket_connect(f"/agent/chat/{session_id}?token={token}") as socket:
        snapshot = socket.receive_json()
        assert snapshot["event"] == "session_snapshot"
        assert snapshot["data"]["messages"] == []
        socket.send_json({"event": "user_message", "data": {
            "session_id": session_id, "text": "¿Cómo hago una devolución?",
        }})
        events = []
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            event = socket.receive_json()
            events.append(event)
            if event["event"] == "generation_completed":
                break
    chunks = [event for event in events if event["event"] == "token_chunk"]
    assert [event["data"]["sequence"] for event in chunks] == [1, 2]
    assert "".join(event["data"]["token"] for event in chunks) == "Respuesta en vivo"
    assert events[-1]["event"] == "generation_completed"
    with client.websocket_connect(f"/agent/chat/{session_id}?token={token}") as socket:
        restored = socket.receive_json()
    assert restored["event"] == "session_snapshot"
    assert [message["role"] for message in restored["data"]["messages"]] == ["user", "assistant"]
    assert restored["data"]["messages"][-1]["text"] == "Respuesta en vivo"
    assert restored["data"]["messages"][-1]["status"] == "completed"


def test_interrupt_cancels_provider_and_keeps_partial_for_new_turn(tmp_path, monkeypatch):
    hub = ChatHub(tmp_path / "agent.sqlite3")
    from services.support_agent import chat as chat_module
    from services.support_agent.chat import ChatSession
    from services.support_agent.execution import AgentExecution
    from services.support_agent.traces import AgentTraceStore
    from services.support_agent.memory import AgentMemoryStore

    session = ChatSession("00000000-0000-0000-0000-000000000003", "first_line_cx", "7", "brand-7")
    hub.register(session)
    queue = hub.subscribe(session.session_id)
    provider_started = Event()

    def fake_execute_agent(graph, traces, owner_id, question, memory, thread_id=None):
        sink = pipeline._generation_sink.get()
        assert sink is not None
        on_token, cancelled, register_abort = sink
        if question == "rastrea":
            aborted = Event()
            register_abort(aborted.set)
            on_token("parcial ")
            provider_started.set()
            assert cancelled.wait(timeout=2)
            # Simulate a provider that yields one already-buffered chunk on close.
            on_token("tardío")
            assert aborted.is_set()
            raise InterruptedError("cancelled")
        on_token("respuesta nueva")
        return AgentExecution("trace-new", "respuesta nueva", None)

    monkeypatch.setattr(chat_module, "execute_agent", fake_execute_agent)
    traces = AgentTraceStore(tmp_path / "traces.sqlite")
    memory = AgentMemoryStore(tmp_path / "agent.sqlite3")
    hub.add_user_message(session, "rastrea")
    hub.start_turn(session, "rastrea", object(), traces, memory)
    assert provider_started.wait(timeout=2)
    hub.interrupt(session, "quiero devolverlo")
    asyncio.run(hub.wait_for_interruption(session))
    interrupted_message = session.messages[-1]
    assert interrupted_message["status"] == "interrupted"
    assert interrupted_message["text"] == "parcial "

    hub.add_user_message(session, "quiero devolverlo")
    hub.start_turn(session, "quiero devolverlo", object(), traces, memory)
    assert session.future is not None
    session.future.result(timeout=2)
    new_message = session.messages[-1]
    assert new_message["status"] == "completed"
    assert new_message["text"] == "respuesta nueva"
    assert new_message["generation_id"] != interrupted_message["generation_id"]

    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    chunks = [event for event in events if event["event"] == "token_chunk"]
    assert [event["data"]["token"] for event in chunks] == ["parcial ", "respuesta nueva"]
    assert chunks[0]["data"]["generation_id"] == interrupted_message["generation_id"]
    assert chunks[1]["data"]["generation_id"] == new_message["generation_id"]
    assert any(event["event"] == "generation_interrupted" for event in events)
    assert any(event["event"] == "generation_completed" for event in events)
    hub.close()
