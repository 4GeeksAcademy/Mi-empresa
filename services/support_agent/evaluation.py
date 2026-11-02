"""Evaluate saved agent traces without running the graph or model."""

from typing import Any


def _nodes(trace: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = trace.get("nodes")
    if not isinstance(nodes, list) or not all(isinstance(node, dict) for node in nodes):
        return []
    return nodes


def _normalized_text(value: Any) -> str:
    return " ".join(str(value).casefold().split())


def evaluate_trace(trace: dict[str, Any]) -> list[tuple[str, bool, str]]:
    question = trace.get("question")
    answer = trace.get("answer")
    nodes = _nodes(trace)
    names = [node.get("node") for node in nodes]
    results: list[tuple[str, bool, str]] = []

    if isinstance(question, str) and not question.strip():
        passed = (
            trace.get("status") == "rejected"
            and trace.get("error_code") == "invalid_question"
            and names == ["receive", "invalid_question"]
        )
        results.append(("empty_question", passed, "empty input routes directly to rejection"))
        return results

    retrieve_nodes = [node for node in nodes if node.get("node") == "retrieve"]
    retrieved_context = (
        retrieve_nodes[0].get("output", {}).get("context")
        if len(retrieve_nodes) == 1
        else None
    )

    if retrieved_context == [] and "no_context" in names:
        passed = (
            trace.get("status") == "completed"
            and names == ["receive", "retrieve", "no_context"]
            and retrieve_nodes[0].get("output", {}).get("route") == "no_context"
            and isinstance(answer, str)
            and "no contiene información suficiente" in answer.casefold()
        )
        results.append(("no_context", passed, "empty retrieval takes the honest-answer route"))
        return results

    flow_passed = (
        trace.get("status") == "completed"
        and names == ["receive", "retrieve", "generate"]
        and len(retrieve_nodes) == 1
        and bool(retrieved_context)
        and retrieve_nodes[0].get("output", {}).get("route") == "generate"
        and nodes[2].get("input", {}).get("context") == retrieved_context
        and all(node.get("status") == "completed" for node in nodes)
    )
    results.append(("flow", flow_passed, "retrieve runs once before generation with its context"))

    is_returns_question = (
        isinstance(question, str)
        and "devolucion" in question.casefold()
        and "internacional" in question.casefold()
    )
    if is_returns_question:
        has_source = any(
            isinstance(chunk, dict)
            and chunk.get("source_document") == "returns-policy"
            and "gestión manual" in _normalized_text(chunk.get("text", ""))
            for chunk in (retrieved_context or [])
        )
        answer_grounded = (
            isinstance(answer, str)
            and "manual" in answer.casefold()
            and "sofía ramos" in _normalized_text(answer)
            and "returns-policy" in _normalized_text(answer)
            and "no confiable" not in _normalized_text(answer)
            and "no puedo dar por seguro" not in _normalized_text(answer)
            and "no constituyen evidencia" not in _normalized_text(answer)
        )
        results.append((
            "briefing_grounding",
            flow_passed and has_source and answer_grounded,
            "international returns answer cites the retrieved manual-handling policy",
        ))

    return results


REQUIRED_CASES = {"flow", "empty_question", "no_context", "briefing_grounding"}
