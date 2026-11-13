"""LangGraph orchestration for the TrackFlow RFP intake workflow.

The graph starts only after PDF-to-Markdown conversion. Department workers receive
Markdown plus extracted metadata, never the source PDF, and execute as parallel
LangGraph branches before the synthesizer creates the Part 2 handoff.
"""
from __future__ import annotations

import operator
from pathlib import Path
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from .pipeline import (
    DEPARTMENTS,
    _department_worker,
    classify_document,
    convert_pdf_to_markdown,
    extract_metadata,
    readability_metrics,
)


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
        return {"department_sections": [
            _department_worker(state["markdown"], state["metadata"], department_id)
        ]}
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


def process_rfp_document_with_graph(pdf_path: Path, markdown_path: Path) -> dict[str, Any]:
    """Convert PDF once, then run classification, parallel routing, and synthesis."""
    markdown = convert_pdf_to_markdown(pdf_path, markdown_path)
    result = RFP_GRAPH.invoke({
        "markdown": markdown,
        "markdown_path": str(markdown_path),
        "department_sections": [],
    })
    if not result["accepted"]:
        return {
            "accepted": False,
            "reason": result["reason"],
            "markdown_path": str(markdown_path),
            "readability_metrics": result["metrics"],
        }
    return {
        "accepted": True,
        "reason": result["reason"],
        "markdown_path": str(markdown_path),
        "metadata": result["metadata"],
        "department_sections": result.get("department_sections", []),
        "handoff": result["handoff"],
    }
