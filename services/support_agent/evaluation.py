"""Evaluate saved agent traces without running the graph or model."""

from typing import Any

from services.support_agent.incidents import FALLBACK, IncidentSuccess, format_incidents


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

    expected_source = trace.get("expected_source")
    selected_source = nodes[0].get("output", {}).get("source") if nodes else None
    if expected_source in {"incidents", "both"} or selected_source in {"incidents", "both"}:
        tool_nodes = [node for node in nodes if node.get("node") == "incidents"]
        tool_output = tool_nodes[0].get("output", {}) if len(tool_nodes) == 1 else {}
        tool_result = tool_output.get("incident_result", {})
        common = (
            trace.get("status") == "completed"
            and len(tool_nodes) == 1
            and names[:2] == ["receive", "incidents"]
            and all(node.get("status") == "completed" for node in nodes)
            and (expected_source is None or expected_source == selected_source)
        )
        succeeded = tool_result.get("ok") is True
        if selected_source == "both":
            expected_names = ["receive", "incidents"]
            if not succeeded:
                expected_names.append("tool_fallback")
            expected_names += ["retrieve", "generate" if "generate" in names else "no_context"]
            results.append((
                "routing_both",
                common and names == expected_names,
                "operational lookup precedes one documentation retrieval",
            ))
        elif succeeded:
            rows = tool_result.get("incidents")
            valid_rows = isinstance(rows, list) and all(
                isinstance(row, dict)
                and all(field in row for field in (
                    "id", "title", "status", "category", "origin", "branch",
                    "created_at", "updated_at",
                ))
                for row in rows
            )
            expected_answer = None
            if valid_rows:
                success: IncidentSuccess = {"ok": True, "incidents": rows}
                expected_answer = format_incidents(success)
            query_id = tool_nodes[0].get("input", {}).get("incident_query", {}).get("ticket_id")
            results.append((
                "routing_tool" if query_id is not None else "routing_list",
                common and names == ["receive", "incidents", "incident_answer"]
                and valid_rows and answer == expected_answer
                and (query_id is None or (len(rows) == 1 and rows[0].get("id") == query_id)),
                "live incident lookup answers from returned fields without RAG",
            ))
        else:
            results.append((
                "tool_fallback",
                common and names == ["receive", "incidents", "tool_fallback", "incident_answer"]
                and tool_result.get("error_code") in {
                    "timeout", "unavailable", "not_found", "authentication",
                    "invalid_response", "invalid_input", "configuration", "http_error",
                }
                and isinstance(answer, str) and answer.startswith(FALLBACK),
                "tool failure takes an explicit honest-answer route without RAG",
            ))
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
    results.append((
        "routing_rag",
        flow_passed and expected_source in {None, "rag"}
        and selected_source in {None, "rag"} and "incidents" not in names,
        "documented policy uses RAG without the incident tool",
    ))

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
EXTERNAL_REQUIRED_CASES = {"routing_tool", "routing_rag"}
