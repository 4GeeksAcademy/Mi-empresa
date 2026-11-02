"""Focused external-tool evals; HTTP stubs here are not live acceptance evidence."""

import asyncio
import time
from unittest.mock import Mock

import httpx
import pytest

from services.support_agent import graph as agent
from services.support_agent import incidents as tool
from services.support_agent.evaluation import evaluate_trace
from services.support_agent.execution import execute_agent
from services.support_agent.routing import decide_sources
from services.support_agent.traces import AgentTraceStore


@pytest.mark.parametrize(("question", "source", "ticket_id"), [
    ("¿En qué estado está el ticket #482?", "incidents", 482),
    ("What is the status of incident 482?", "incidents", 482),
    ("¿Cuál es la política de devoluciones internacionales?", "rag", None),
    ("¿Qué significa que una incidencia esté abierta?", "rag", None),
    ("¿Cómo va el ticket 482?", "incidents", 482),
    ("¿En qué estado está el ticket 482 y qué política aplica?", "both", 482),
    ("Lista las incidencias abiertas de Zaragoza", "incidents", None),
])
def test_automatic_source_selection(question, source, ticket_id):
    decision = decide_sources(question)
    assert decision["source"] == source
    if ticket_id is not None:
        assert decision["query"].ticket_id == ticket_id


@pytest.mark.parametrize("question", [
    "Estado de los tickets 1 y ticket 2",
    "Estado de los tickets 1 y 2",
    "Estado del ticket 0",
    "Estado del ticket",
    "Lista incidencias abiertas y resueltas",
])
def test_ambiguous_operational_input_requires_clarification(question):
    decision = decide_sources(question)
    assert decision["source"] == "incidents"
    assert decision["query"] is None


@pytest.mark.parametrize(("status", "payload", "expected"), [
    (404, {}, "not_found"),
    (401, {}, "authentication"),
    (403, {}, "authentication"),
    (503, {}, "unavailable"),
    (302, {}, "http_error"),
    (200, {"status": "invented"}, "invalid_response"),
])
def test_http_failure_contract_is_sanitized(monkeypatch, status, payload, expected):
    original_client = httpx.AsyncClient

    async def handler(request):
        assert request.method == "GET"
        assert request.url.path == "/api/incidents/482"
        assert request.headers["Authorization"] == "Bearer local-unit-test"
        return httpx.Response(status, json=payload)

    monkeypatch.setenv("TRACKFLOW_INCIDENTS_TOKEN", "local-unit-test")
    monkeypatch.setattr(tool.httpx, "AsyncClient", lambda **kwargs: original_client(
        **kwargs, transport=httpx.MockTransport(handler),
    ))
    result = tool.query_incidents(tool.IncidentQuery(ticket_id=482))
    assert result == {"ok": False, "error_code": expected}
    assert "local-unit-test" not in str(result)


def test_total_http_deadline_is_effective(monkeypatch):
    original_client = httpx.AsyncClient

    async def handler(request):
        await asyncio.sleep(tool.TIMEOUT_SECONDS + 1)
        return httpx.Response(200, json=[])

    monkeypatch.setattr(tool.httpx, "AsyncClient", lambda **kwargs: original_client(
        **kwargs, transport=httpx.MockTransport(handler),
    ))
    started = time.monotonic()
    result = tool.query_incidents(tool.IncidentQuery())
    elapsed = time.monotonic() - started
    assert tool.TIMEOUT_SECONDS == 5.0
    assert result == {"ok": False, "error_code": "timeout"}
    assert 4.9 <= elapsed < 5.5


def test_explicit_fallback_trace_passes_evaluation(tmp_path, monkeypatch):
    monkeypatch.setattr(
        agent, "query_incidents",
        Mock(return_value={"ok": False, "error_code": "not_found"}),
    )
    retrieve = Mock(side_effect=AssertionError("RAG must not replace live data"))
    monkeypatch.setattr(agent.pipeline, "retrieve", retrieve)
    database = tmp_path / "agent.sqlite3"
    traces = AgentTraceStore(database)
    traces.setup()
    with agent.open_agent_graph(database) as graph:
        execution = execute_agent(graph, traces, "unit-eval", "Estado del ticket 482")
    trace = traces.get_for_owner(execution.trace_id, "unit-eval")
    assert evaluate_trace(trace)[0][:2] == ("tool_fallback", True)
    assert execution.answer.startswith(tool.FALLBACK)
    retrieve.assert_not_called()


@pytest.mark.parametrize("succeeded", [True, False])
def test_both_sources_trace_orders_tool_before_rag(tmp_path, monkeypatch, succeeded):
    result = (
        {"ok": True, "incidents": []}
        if succeeded else {"ok": False, "error_code": "timeout"}
    )
    monkeypatch.setattr(agent, "query_incidents", Mock(return_value=result))
    context = [{"text": "Política documentada."}]
    monkeypatch.setattr(agent.pipeline, "retrieve", Mock(return_value=context))
    generate = Mock(return_value="Respuesta de política.")
    monkeypatch.setattr(agent.pipeline, "generate_answer", generate)
    database = tmp_path / "agent.sqlite3"
    traces = AgentTraceStore(database)
    traces.setup()
    with agent.open_agent_graph(database) as graph:
        execution = execute_agent(
            graph, traces, "unit-eval", "Estado del ticket 482 y qué política aplica",
        )
    trace = traces.get_for_owner(execution.trace_id, "unit-eval")
    assert evaluate_trace(trace)[0][:2] == ("routing_both", True)
    assert generate.call_args.args[1] == context
    assert "No afirmes ningún estado" in generate.call_args.args[0]
    if not succeeded:
        assert execution.answer.startswith(tool.FALLBACK)


def test_existing_ticket_routing_eval_checks_returned_id(tmp_path, monkeypatch):
    row = {
        "id": 482, "title": "Unit test only", "description": "Not live evidence",
        "category": "tracking", "status": "open", "origin": "customer",
        "branch": "zaragoza", "created_at": "2026-11-01T00:00:00Z",
        "updated_at": "2026-11-01T00:00:00Z",
    }
    monkeypatch.setattr(
        agent, "query_incidents", Mock(return_value={"ok": True, "incidents": [row]}),
    )
    monkeypatch.setattr(
        agent.pipeline, "retrieve", Mock(side_effect=AssertionError("Unexpected RAG")),
    )
    database = tmp_path / "agent.sqlite3"
    traces = AgentTraceStore(database)
    traces.setup()
    with agent.open_agent_graph(database) as graph:
        execution = execute_agent(graph, traces, "unit-eval", "Estado del ticket 482")
    trace = traces.get_for_owner(execution.trace_id, "unit-eval")
    assert evaluate_trace(trace)[0][:2] == ("routing_tool", True)
    trace["nodes"][1]["input"]["incident_query"]["ticket_id"] = 483
    assert evaluate_trace(trace)[0][:2] == ("routing_tool", False)
