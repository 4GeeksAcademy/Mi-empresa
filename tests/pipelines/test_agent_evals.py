import json
from pathlib import Path

import pytest

from scripts.evaluate_agent_traces import load_traces
from services.support_agent.evaluation import evaluate_trace

TRACE_FIXTURE = Path(__file__).parent / "fixtures" / "agent_traces.json"
LIVE_TRACE_FIXTURE = Path(__file__).parent / "fixtures" / "agent-trace-returns.json"


@pytest.fixture(scope="module")
def traces():
    return {trace["trace_id"]: trace for trace in json.loads(TRACE_FIXTURE.read_text())}


def test_evaluation_traces_run_receive_then_retrieve_then_generate_once(traces):
    trace = traces["11111111-1111-4111-8111-111111111111"]

    assert trace["status"] == "completed"
    assert [node["node"] for node in trace["nodes"]] == [
        "receive", "retrieve", "generate",
    ]
    assert [node["order"] for node in trace["nodes"]] == [1, 2, 3]
    assert all(node["status"] == "completed" for node in trace["nodes"])
    assert sum(node["node"] == "retrieve" for node in trace["nodes"]) == 1
    assert (
        trace["nodes"][2]["input"]["context"]
        == trace["nodes"][1]["output"]["context"]
    )
    assert ("flow", True, "retrieve runs once before generation with its context") in evaluate_trace(trace)


def test_evaluation_empty_question_stops_before_retrieval(traces):
    trace = traces["22222222-2222-4222-8222-222222222222"]

    assert trace["status"] == "rejected"
    assert trace["error_code"] == "invalid_question"
    assert [node["node"] for node in trace["nodes"]] == [
        "receive", "invalid_question",
    ]
    assert evaluate_trace(trace)[0][0:2] == ("empty_question", True)


def test_evaluation_missing_context_takes_honest_route_without_generation(traces):
    trace = traces["33333333-3333-4333-8333-333333333333"]

    assert trace["status"] == "completed"
    assert [node["node"] for node in trace["nodes"]] == [
        "receive", "retrieve", "no_context",
    ]
    assert trace["nodes"][1]["output"]["context"] == []
    assert trace["nodes"][1]["output"]["route"] == "no_context"
    assert "no contiene información suficiente" in trace["answer"]
    assert evaluate_trace(trace)[0][0:2] == ("no_context", True)


def test_evaluation_grounding_matches_real_returns_policy_contract(traces):
    trace = traces["11111111-1111-4111-8111-111111111111"]
    retrieved = trace["nodes"][1]["output"]["context"]
    expected_source = "returns-policy"
    expected_fact = "requieren gestión manual"

    assert any(chunk["source_document"] == expected_source for chunk in retrieved)
    assert expected_fact in trace["answer"].casefold()
    assert expected_source in trace["answer"]
    assert ("briefing_grounding", True, "international returns answer cites the retrieved manual-handling policy") in evaluate_trace(trace)


def test_acceptance_evaluator_refuses_synthetic_fixtures():
    with pytest.raises(ValueError, match="Refusing synthetic test fixture"):
        load_traces([TRACE_FIXTURE])


def test_grounding_eval_normalizes_line_breaks_in_retrieved_source(traces):
    trace = traces["11111111-1111-4111-8111-111111111111"]
    retrieved = trace["nodes"][1]["output"]["context"][0]
    retrieved["text"] = (
        "Las devoluciones internacionales requieren gestión\n"
        "manual del equipo de Sofía Ramos."
    )
    trace["nodes"][2]["input"]["context"][0]["text"] = retrieved["text"]

    assert ("briefing_grounding", True, "international returns answer cites the retrieved manual-handling policy") in evaluate_trace(trace)


def test_authorized_live_trace_passes_grounding_eval():
    trace = json.loads(LIVE_TRACE_FIXTURE.read_text(encoding="utf-8"))
    assert trace["origin"] == "authorized_live_provider_run"
    assert ("briefing_grounding", True, "international returns answer cites the retrieved manual-handling policy") in evaluate_trace(trace)
