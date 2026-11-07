from unittest.mock import Mock

import pytest
from langgraph.graph import END, START, StateGraph

from services.support_agent import graph as agent


@pytest.fixture
def context():
    return [{
        "company": "trackflow",
        "source_document": "returns-policy",
        "section": "Política de Devoluciones",
        "language": "es",
        "chunk_index": 0,
        "text": "Las devoluciones internacionales requieren gestión manual.",
    }]


def test_graph_retrieves_once_and_generates_from_the_same_context(tmp_path, monkeypatch, context):
    retrieve = Mock(return_value=context)
    generate = Mock(return_value="Requieren gestión manual. [returns-policy]")
    monkeypatch.setattr(agent.pipeline, "retrieve", retrieve)
    monkeypatch.setattr(agent.pipeline, "generate_answer", generate)
    config = {"configurable": {"thread_id": "successful-run"}}

    with agent.open_agent_graph(tmp_path / "checkpoints.sqlite3") as graph:
        updates = list(graph.stream(
            {"question": "  ¿Cómo funcionan las devoluciones internacionales?  "},
            config, stream_mode="updates", durability="sync",
        ))
        state = graph.get_state(config)

    assert [next(iter(update)) for update in updates] == ["receive", "retrieve", "generate"]
    retrieve.assert_called_once_with("¿Cómo funcionan las devoluciones internacionales?")
    generate.assert_called_once_with(retrieve.call_args.args[0], context, country=None)
    assert state.values["answer"] == generate.return_value
    assert state.values["error"] is None
    assert state.next == ()


@pytest.mark.parametrize("question", ["", "  \n\t "])
def test_empty_question_ends_without_retrieving_or_generating(tmp_path, monkeypatch, question):
    retrieve = Mock()
    generate = Mock()
    monkeypatch.setattr(agent.pipeline, "retrieve", retrieve)
    monkeypatch.setattr(agent.pipeline, "generate_answer", generate)

    with agent.open_agent_graph(tmp_path / "checkpoints.sqlite3") as graph:
        result = graph.invoke(
            {"question": question}, {"configurable": {"thread_id": "empty-run"}},
            durability="sync",
        )

    assert result["error"] == agent.INVALID_QUESTION
    assert result["answer"] == ""
    retrieve.assert_not_called()
    generate.assert_not_called()


def test_no_context_ends_with_honest_answer_without_generation(tmp_path, monkeypatch):
    monkeypatch.setattr(agent.pipeline, "retrieve", Mock(return_value=[]))
    generate = Mock()
    monkeypatch.setattr(agent.pipeline, "generate_answer", generate)

    with agent.open_agent_graph(tmp_path / "checkpoints.sqlite3") as graph:
        updates = list(graph.stream(
            {"question": "¿Existe esta condición no documentada?"},
            {"configurable": {"thread_id": "no-context-run"}},
            stream_mode="updates", durability="sync",
        ))

    assert [next(iter(update)) for update in updates] == ["receive", "retrieve", "no_context"]
    assert updates[-1]["no_context"]["answer"] == agent.NO_CONTEXT
    generate.assert_not_called()


def test_checkpoint_survives_reopen_and_resumes_without_retrieval(tmp_path, monkeypatch, context):
    database = tmp_path / "checkpoints.sqlite3"
    config = {"configurable": {"thread_id": "resumable-run"}}
    retrieve = Mock(return_value=context)
    generate = Mock(side_effect=RuntimeError("Generation temporarily unavailable"))
    monkeypatch.setattr(agent.pipeline, "retrieve", retrieve)
    monkeypatch.setattr(agent.pipeline, "generate_answer", generate)

    with agent.open_agent_graph(database) as graph:
        with pytest.raises(RuntimeError, match="temporarily unavailable"):
            graph.invoke(
                {"question": "¿Cómo se gestionan las devoluciones internacionales?"},
                config, durability="sync",
            )
        assert graph.get_state(config).next == ("generate",)

    generate.side_effect = None
    generate.return_value = "Requieren gestión manual. [returns-policy]"
    with agent.open_agent_graph(database) as graph:
        history = list(graph.get_state_history(config))
        assert any(
            snapshot.next == ("generate",) and snapshot.values["context"] == context
            for snapshot in history
        )
        result = graph.invoke(None, config, durability="sync")
        assert graph.get_state(config).next == ()

    assert result["answer"] == generate.return_value
    retrieve.assert_called_once()
    assert generate.call_count == 2


def test_distinct_threads_do_not_share_state(tmp_path, monkeypatch, context):
    monkeypatch.setattr(agent.pipeline, "retrieve", Mock(return_value=context))
    monkeypatch.setattr(agent.pipeline, "generate_answer", Mock(return_value="Respuesta uno"))
    first = {"configurable": {"thread_id": "first-run"}}
    second = {"configurable": {"thread_id": "second-run"}}

    with agent.open_agent_graph(tmp_path / "checkpoints.sqlite3") as graph:
        graph.invoke({"question": "Primera pregunta"}, first, durability="sync")
        graph.invoke({"question": ""}, second, durability="sync")
        assert graph.get_state(first).values["answer"] == "Respuesta uno"
        assert graph.get_state(second).values["answer"] == ""
        assert graph.get_state(second).values["context"] == []


def test_compilation_rejects_unknown_transition_target(tmp_path, monkeypatch):
    builder = StateGraph(agent.AgentState, input_schema=agent.AgentInput)
    builder.add_node("receive", agent.receive_question)
    builder.add_edge(START, "receive")
    builder.add_edge("receive", "missing")
    monkeypatch.setattr(agent, "build_agent_graph", lambda: builder)

    with pytest.raises(agent.AgentGraphError, match="Cannot compile agent graph"):
        with agent.open_agent_graph(tmp_path / "checkpoints.sqlite3"):
            pytest.fail("Invalid graph must not be exposed")


def test_compilation_rejects_disconnected_node(tmp_path, monkeypatch):
    builder = agent.build_agent_graph()
    builder.add_node("orphan", agent.no_context)
    builder.add_edge("orphan", END)
    monkeypatch.setattr(agent, "build_agent_graph", lambda: builder)

    with pytest.raises(agent.AgentGraphError, match="orphan"):
        with agent.open_agent_graph(tmp_path / "checkpoints.sqlite3"):
            pytest.fail("Disconnected graph must not be exposed")


def test_receive_rejects_non_string_input():
    with pytest.raises(ValueError, match="debe ser un texto"):
        agent.receive_question({"question": None})  # type: ignore[typeddict-item]
