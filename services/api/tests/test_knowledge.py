from fastapi.testclient import TestClient

from auth import get_current_user
from main import app
from routes import knowledge


def test_knowledge_query_returns_generated_answer_only(monkeypatch):
    called = []

    def fake_query(question: str) -> str:
        called.append(question)
        return "El envío estándar tarda de 3 a 5 días hábiles."

    monkeypatch.setattr(knowledge, "query", fake_query)
    app.dependency_overrides[get_current_user] = lambda: {"id": "test-user"}
    try:
        response = TestClient(app).post(
            "/knowledge/query",
            json={"question": "¿Cuál es el SLA estándar?"},
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    assert response.status_code == 200
    assert response.json() == {"answer": "El envío estándar tarda de 3 a 5 días hábiles."}
    assert called == ["¿Cuál es el SLA estándar?"]


def test_knowledge_query_rejects_empty_question():
    app.dependency_overrides[get_current_user] = lambda: {"id": "test-user"}
    try:
        response = TestClient(app).post("/knowledge/query", json={"question": "   "})
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    assert response.status_code == 422
