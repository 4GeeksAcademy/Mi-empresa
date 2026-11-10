"""LangGraph orchestration for TrackFlow RFP intake.

Conversion is completed before invoking this graph. Its state contains Markdown,
never the PDF, and department branches run in parallel before synthesis.
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from data.pipelines.rfp_intake.pipeline import DEPARTMENTS, classify_document, extract_metadata, readability_metrics


class RfpGraphState(TypedDict, total=False):
    markdown: str
    markdown_path: str
    accepted: bool
    reason: str
    metadata: dict[str, Any]
    metrics: dict[str, float | int | bool]
    department_sections: Annotated[list[dict[str, Any]], operator.add]
    handoff: dict[str, Any]


def _classify(state: RfpGraphState) -> dict[str, Any]:
    accepted, reason = classify_document(state["markdown"])
    return {"accepted": accepted, "reason": reason, "metrics": readability_metrics(state["markdown"])}


def _extract(state: RfpGraphState) -> dict[str, Any]:
    metadata = extract_metadata(state["markdown"])
    metadata["readability_metrics"] = state["metrics"]
    return {"metadata": metadata}


def _dispatch(state: RfpGraphState) -> list[Send] | str:
    departments = state["metadata"]["departments_needed"]
    if not departments:
        return "synthesize"
    return [Send(f"{department}_worker", state) for department in departments]


def _worker(department_id: str):
    def run(state: RfpGraphState) -> dict[str, Any]:
        markdown = state["markdown"]
        metadata = state["metadata"]
        lower = markdown.casefold()
        terms = DEPARTMENTS[department_id]["terms"]
        matched = [line.strip() for line in markdown.splitlines()
                   if any(term in line.casefold() for term in terms)]
        questions = []
        if department_id == "warehouse" and metadata["monthly_volume"] is None:
            questions.append("What is the expected monthly order volume and storage footprint?")
        if department_id == "lastmile" and metadata["client_country"] is None:
            questions.append("Which destination country/regions and delivery SLA are required?")
        if department_id == "reverse" and not any(term in lower for term in ("return rate", "devoluciones", "returns")):
            questions.append("What return volume and processing requirements should be planned?")
        return {"department_sections": [{
            "department_id": department_id,
            "approver": DEPARTMENTS[department_id]["approver"],
            "key_aspects": matched[:8],
            "open_questions": questions,
            "source_extract": "\n".join(matched)[:4000],
        }]}
    return run


def _synthesize(state: RfpGraphState) -> dict[str, Any]:
    return {"handoff": {
        "ticket_id": None,
        "metadata": state["metadata"],
        "department_workstreams": state.get("department_sections", []),
        "source_markdown_path": state["markdown_path"],
        "contract_version": "1.0",
    }}


def _build_graph():
    graph = StateGraph(RfpGraphState)
    graph.add_node("classify", _classify)
    graph.add_node("extract", _extract)
    graph.add_node("dispatch", lambda _state: {})
    graph.add_node("reject", lambda _state: {})
    graph.add_node("synthesize", _synthesize)
    for department_id in DEPARTMENTS:
        graph.add_node(f"{department_id}_worker", _worker(department_id))
        graph.add_edge(f"{department_id}_worker", "synthesize")
    graph.add_edge(START, "classify")
    graph.add_conditional_edges("classify", lambda state: "extract" if state["accepted"] else "reject")
    graph.add_edge("extract", "dispatch")
    graph.add_conditional_edges("dispatch", _dispatch)
    graph.add_edge("synthesize", END)
    graph.add_edge("reject", END)
    return graph.compile()


RFP_GRAPH = _build_graph()


def process_rfp_markdown(markdown: str, markdown_path: str) -> dict[str, Any]:
    """Run the graph against an already converted and persisted Markdown document."""
    result = RFP_GRAPH.invoke({
        "markdown": markdown,
        "markdown_path": markdown_path,
        "department_sections": [],
    })
    if not result["accepted"]:
        return {
            "accepted": False,
            "reason": result["reason"],
            "markdown_path": markdown_path,
            "readability_metrics": result["metrics"],
        }
    return {
        "accepted": True,
        "reason": result["reason"],
        "markdown_path": markdown_path,
        "metadata": result["metadata"],
        "department_sections": result.get("department_sections", []),
        "handoff": result["handoff"],
    }
