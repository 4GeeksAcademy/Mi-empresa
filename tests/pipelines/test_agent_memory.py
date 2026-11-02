from unittest.mock import Mock
from datetime import datetime, timedelta, timezone

import pytest

from services.support_agent.execution import execute_agent
from services.support_agent.memory import AgentMemoryStore, propose_memory
from services.support_agent.traces import AgentTraceStore
from services.support_agent.graph import open_agent_graph
from services.support_agent.evaluation import evaluate_trace
from services.knowledge import pipeline
from services.support_agent import memory as memory_module


@pytest.mark.parametrize("message", [
    "¿Dónde está el paquete con tracking XJ4471?",
    "Perfecto, ya quedó resuelto.",
    "Tradúceme esto al inglés para el cliente.",
    "La dirección de entrega es Calle Mayor 12345.",
    "El contrato está en negociación activa.",
    "Revisa la ruta interna del almacén de Zaragoza.",
])
def test_non_memorable_or_forbidden_messages_do_not_propose_memory(message):
    assert propose_memory(message) is None


def _stores(tmp_path):
    database = tmp_path / "agent.sqlite3"
    memory = AgentMemoryStore(database)
    memory.setup()
    traces = AgentTraceStore(database)
    traces.setup()
    return database, memory, traces


@pytest.mark.parametrize(("message", "expected_action"), [
    ("aprobar", "approved"),
    ("rechazar", "rejected"),
    ("aprobar, ¿qué política aplica?", "approved"),
    ("rechazar, ¿qué política aplica?", "rejected"),
    ("aprobar, no la guardes", "rejected"),
    ("aprobar, no estoy seguro", "rejected"),
])
def test_advertised_consent_commands(tmp_path, message, expected_action):
    _, memory, _ = _stores(tmp_path)
    draft = propose_memory(
        "SEUR ya no cubre zonas rurales de Zaragoza; usa el carrier local."
    )
    assert draft is not None
    memory.propose("cx-user", draft)

    resolution = memory.resolve_pending("cx-user", message)

    assert resolution.action == expected_action
    assert bool(memory.list_memories()) == (expected_action == "approved")
    assert memory.list_audit("cx-user")["proposals"][0]["status"] == expected_action
    if "política" in message:
        assert resolution.question == "¿qué política aplica?"


def test_carrier_coverage_change_preserves_meaning_and_geography():
    message = "SEUR cambió su cobertura en España y ahora cubre nuevas zonas."

    draft = propose_memory(message)

    assert draft is not None
    assert draft.category == "carrier_rule"
    assert draft.content == message
    assert "Zaragoza" not in draft.content
    assert "zaragoza" not in draft.memory_key
    assert "ya no cubre" not in draft.content


@pytest.mark.parametrize(("preference", "expected"), [
    ("en PDF", "formato PDF"),
    (
        "con devoluciones antes que volumen de envíos",
        "devoluciones antes que volumen de envíos",
    ),
    (
        "con volumen de envíos antes que devoluciones",
        "volumen de envíos antes que devoluciones",
    ),
    (
        "en PDF con devoluciones antes que volumen de envíos",
        "formato PDF; devoluciones antes que volumen de envíos",
    ),
])
def test_report_preference_preserves_format_and_metric_order(preference, expected):
    draft = propose_memory(
        f"El cliente de cosméticos siempre quiere su reporte mensual {preference}."
    )

    assert draft is not None
    assert expected in draft.content
    if preference == "en PDF":
        assert "devoluciones" not in draft.content
    assert "el orden de métricas indicado por el cliente" not in draft.content


def test_unspecified_report_preference_does_not_invent_details():
    assert propose_memory(
        "El cliente de cosméticos siempre quiere su reporte mensual."
    ) is None


def test_approved_carrier_memory_is_used_in_a_later_interaction(
    tmp_path, monkeypatch,
):
    database, memory, traces = _stores(tmp_path)
    monkeypatch.setattr(pipeline, "retrieve", Mock(return_value=[]))
    generate = Mock(side_effect=AssertionError("Memory answer should not call RAG generation"))
    monkeypatch.setattr(pipeline, "generate_answer", generate)
    first_question = (
        "En realidad SEUR ya no cubre esa zona rural de Zaragoza, "
        "hay que usar el carrier local desde el mes pasado."
    )

    with open_agent_graph(database) as graph:
        proposed = execute_agent(
            graph, traces, "cx-user", first_question, memory,
        )
        assert proposed.propuesta_memoria is not None
        assert memory.list_memories() == []

        approved = execute_agent(
            graph,
            traces,
            "cx-user",
            "Sí, ¿qué carrier usamos para zonas rurales de Zaragoza?",
            memory,
        )
        shared = execute_agent(
            graph,
            traces,
            "another-cx-agent",
            "¿Qué carrier usamos para zonas rurales de Zaragoza?",
            memory,
        )

    assert approved.propuesta_memoria is None
    assert "Propuesta aprobada" in approved.answer
    assert "SEUR ya no cubre zonas rurales de Zaragoza" in shared.answer
    assert memory.list_memories()[0]["content"].startswith(
        "SEUR ya no cubre zonas rurales de Zaragoza"
    )
    assert memory.relevant_memories(
        "¿Qué carrier usamos para zonas rurales de Zaragoza?",
    )
    assert memory.list_audit("cx-user")["proposals"][0]["status"] == "approved"
    approved_trace = traces.get_for_owner(approved.trace_id, "cx-user")
    assert evaluate_trace(approved_trace)[0][:2] == ("memory_answer", True)
    generate.assert_not_called()


def test_rejected_b2b_preference_is_audited_without_changing_memory(
    tmp_path, monkeypatch,
):
    database, memory, traces = _stores(tmp_path)
    context = [{
        "company": "trackflow",
        "source_document": "returns-policy",
        "section": "Política de Devoluciones",
        "language": "es",
        "chunk_index": 0,
        "text": "Las devoluciones internacionales requieren gestión manual.",
    }]
    monkeypatch.setattr(pipeline, "retrieve", Mock(return_value=context))
    monkeypatch.setattr(pipeline, "generate_answer", Mock(return_value="Respuesta de política."))
    first_question = (
        "El cliente de cosméticos siempre quiere su reporte mensual con el "
        "desglose de devoluciones primero, antes que el volumen de envíos."
    )

    with open_agent_graph(database) as graph:
        proposed = execute_agent(
            graph, traces, "cx-user", first_question, memory,
        )
        assert proposed.propuesta_memoria is not None
        assert memory.list_memories() == []

        rejected = execute_agent(
            graph,
            traces,
            "cx-user",
            "No, además ¿qué política aplica a devoluciones internacionales?",
            memory,
        )

    assert "la memoria no cambia" in rejected.answer
    assert rejected.answer.endswith("Respuesta de política.")
    assert rejected.propuesta_memoria is None
    assert memory.list_memories() == []
    audit = memory.list_audit("cx-user")
    assert audit["proposals"][0]["status"] == "rejected"
    assert audit["proposals"][0]["result"] == "rejected_memory_unchanged"
    assert any(event["action"] == "rejected" for event in audit["events"])


def test_edit_creates_a_new_pending_proposal_without_saving(
    tmp_path,
):
    _, memory, _ = _stores(tmp_path)
    original = propose_memory(
        "En realidad SEUR ya no cubre esa zona rural de Zaragoza; "
        "hay que usar el carrier local."
    )
    assert original is not None
    first = memory.propose("cx-user", original)
    assert first is not None

    edited = memory.resolve_pending(
        "cx-user",
        "Edita: En realidad MRW ya no cubre esa zona rural de Zaragoza; "
        "hay que usar el carrier local.",
    )

    assert edited.action == "edited"
    assert edited.proposal is not None
    assert edited.proposal["contenido"].startswith(
        "MRW ya no cubre zonas rurales de Zaragoza"
    )
    assert memory.list_memories() == []
    audit = memory.list_audit("cx-user")
    assert audit["proposals"][0]["status"] == "pending"
    assert audit["proposals"][1]["status"] == "edited"


def test_only_one_proposal_can_be_pending_across_agents(tmp_path):
    _, memory, _ = _stores(tmp_path)
    draft = propose_memory(
        "En realidad SEUR ya no cubre esa zona rural de Zaragoza; "
        "hay que usar el carrier local."
    )
    assert draft is not None

    first = memory.propose("cx-user-1", draft)
    blocked = memory.propose("cx-user-2", draft)

    assert first is not None
    assert blocked is None
    assert memory.list_audit("cx-user-2")["proposals"] == []


@pytest.mark.parametrize(("message", "expected_result"), [
    ("Sí, no la guardes", "rejected_memory_unchanged"),
    ("Sí, no lo recuerdes", "rejected_memory_unchanged"),
    ("Sí, no estoy seguro", "ambiguous_default_rejected_memory_unchanged"),
])
def test_rejection_or_uncertainty_overrides_leading_approval(
    tmp_path, message, expected_result,
):
    _, memory, _ = _stores(tmp_path)
    draft = propose_memory(
        "En realidad SEUR ya no cubre esa zona rural de Zaragoza; "
        "hay que usar el carrier local."
    )
    assert draft is not None
    memory.propose("cx-user", draft)

    resolution = memory.resolve_pending("cx-user", message)

    assert resolution.action == "rejected"
    assert memory.list_memories() == []
    audit = memory.list_audit("cx-user")
    assert audit["proposals"][0]["status"] == "rejected"
    assert audit["proposals"][0]["result"] == expected_result


def test_ambiguous_decision_defaults_to_rejection_and_processes_message(tmp_path):
    _, memory, _ = _stores(tmp_path)
    draft = propose_memory(
        "En realidad SEUR ya no cubre esa zona rural de Zaragoza; "
        "hay que usar el carrier local."
    )
    assert draft is not None
    memory.propose("cx-user", draft)

    resolution = memory.resolve_pending(
        "cx-user", "No estoy seguro; ¿qué política aplica a devoluciones?"
    )

    assert resolution.action == "rejected"
    assert resolution.question == "No estoy seguro; ¿qué política aplica a devoluciones?"
    assert memory.list_memories() == []
    audit = memory.list_audit("cx-user")
    assert audit["proposals"][0]["status"] == "rejected"
    assert audit["proposals"][0]["result"] == (
        "ambiguous_default_rejected_memory_unchanged"
    )
    assert any(event["action"] == "ambiguous_rejected" for event in audit["events"])


def test_invalid_edit_defaults_to_rejection(tmp_path):
    _, memory, _ = _stores(tmp_path)
    draft = propose_memory(
        "En realidad SEUR ya no cubre esa zona rural de Zaragoza; "
        "hay que usar el carrier local."
    )
    assert draft is not None
    memory.propose("cx-user", draft)

    resolution = memory.resolve_pending("cx-user", "Edita: recuerda la dirección exacta.")

    assert resolution.action == "rejected"
    assert resolution.question == "recuerda la dirección exacta."
    assert memory.list_memories() == []
    audit = memory.list_audit("cx-user")
    assert audit["proposals"][0]["status"] == "rejected"
    assert audit["proposals"][0]["result"] == (
        "invalid_edit_default_rejected_memory_unchanged"
    )


@pytest.mark.parametrize(("seconds", "expected_action"), [
    (1799, "approved"),
    (1800, "expired"),
    (1801, "expired"),
])
def test_confirmation_respects_exact_proposal_expiry_boundary(
    tmp_path, monkeypatch, seconds, expected_action,
):
    start = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(memory_module, "_timestamp", lambda: start.isoformat())
    _, memory, _ = _stores(tmp_path)
    draft = propose_memory(
        "En realidad SEUR ya no cubre esa zona rural de Zaragoza; "
        "hay que usar el carrier local."
    )
    assert draft is not None
    proposal = memory.propose("cx-user", draft)
    assert proposal is not None
    later = start + timedelta(seconds=seconds)
    monkeypatch.setattr(memory_module, "_timestamp", lambda: later.isoformat())

    resolution = memory.resolve_pending("cx-user", "Sí")

    assert resolution.action == expected_action
    assert bool(memory.list_memories()) == (expected_action == "approved")
    audit = memory.list_audit("cx-user")
    assert len(audit["proposals"]) == 1
    if expected_action == "expired":
        row = audit["proposals"][0]
        assert row["status"] == "discarded"
        assert row["decision"] == "expired"
        assert row["decided_at"] == later.isoformat()
        assert row["result"] == "expired_without_confirmation_memory_unchanged"
        assert len([
            event for event in audit["events"]
            if event["action"] == "expired"
        ]) == 1


@pytest.mark.parametrize("access", ["propose", "audit", "setup", "consolidate"])
def test_expiry_unblocks_other_users_without_changing_approved_memory(
    tmp_path, monkeypatch, access,
):
    start = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(memory_module, "_timestamp", lambda: start.isoformat())
    database, memory, _ = _stores(tmp_path)
    draft = propose_memory(
        "En realidad SEUR ya no cubre esa zona rural de Zaragoza; "
        "hay que usar el carrier local."
    )
    assert draft is not None
    first = memory.propose("cx-user-1", draft)
    assert first is not None
    later = start + timedelta(minutes=30)
    monkeypatch.setattr(memory_module, "_timestamp", lambda: later.isoformat())

    if access == "audit":
        memory.list_audit("cx-user-1")
    elif access == "setup":
        memory = AgentMemoryStore(database)
        memory.setup()
    elif access == "consolidate":
        memory.consolidate()
    replacement = memory.propose("cx-user-2", draft)

    assert replacement is not None
    assert replacement["id"] != first["id"]
    assert memory.list_memories() == []
    assert memory.list_audit("cx-user-1")["proposals"][0]["decision"] == "expired"
    memory.list_audit("cx-user-1")
    assert len([
        event for event in memory.list_audit("cx-user-1")["events"]
        if event["action"] == "expired"
    ]) == 1


def test_expired_confirmation_still_answers_remaining_question(
    tmp_path, monkeypatch,
):
    start = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(memory_module, "_timestamp", lambda: start.isoformat())
    database, memory, traces = _stores(tmp_path)
    draft = propose_memory(
        "En realidad SEUR ya no cubre esa zona rural de Zaragoza; "
        "hay que usar el carrier local."
    )
    assert draft is not None
    memory.propose("cx-user", draft)
    monkeypatch.setattr(
        memory_module, "_timestamp",
        lambda: (start + timedelta(minutes=30)).isoformat(),
    )
    monkeypatch.setattr(pipeline, "retrieve", Mock(return_value=[]))
    with open_agent_graph(database) as graph:
        result = execute_agent(
            graph, traces, "cx-user",
            "Sí, ¿qué política aplica a devoluciones?", memory,
        )

    assert result.error is None
    assert "caducó tras 30 minutos" in result.answer
    assert "no contiene información suficiente" in result.answer
    assert result.propuesta_memoria is None
    assert memory.list_memories() == []
