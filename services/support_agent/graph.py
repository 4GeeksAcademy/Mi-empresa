"""Compile the RAG flow and persist its state without retaining chat history."""

import logging
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from services.knowledge import pipeline
from services.support_agent.incidents import (
    FALLBACK, IncidentQuery, IncidentResult, failure, format_incidents, query_incidents,
)
from services.support_agent.routing import decide_sources

logger = logging.getLogger("trackflow_api.support_agent")

INVALID_QUESTION = "La pregunta no puede estar vacía."
NO_CONTEXT = (
    "La base de conocimiento no contiene información suficiente para responder. "
    "Confirma la condición con el equipo responsable antes de prometerla."
)


class AgentInput(TypedDict):
    question: str


class AgentState(AgentInput):
    context: list[dict[str, str | int]]
    answer: str
    error: str | None
    route: Literal[
        "retrieve", "incidents", "invalid_question", "generate", "no_context",
        "incident_answer", "tool_fallback",
    ]
    source: Literal["rag", "incidents", "both"]
    incident_query: dict[str, str | int | None] | None
    incident_result: IncidentResult | None


class AnswerUpdate(TypedDict):
    answer: str


class ContextUpdate(TypedDict):
    context: list[dict[str, str | int]]
    route: Literal["generate", "no_context"]


class ErrorUpdate(TypedDict):
    error: str


class AgentGraphError(RuntimeError):
    """The agent graph cannot be safely compiled."""


def receive_question(state: AgentInput) -> AgentState:
    question = state.get("question")
    if not isinstance(question, str):
        raise ValueError("La pregunta debe ser un texto.")
    normalized_question = question.strip()
    decision = decide_sources(normalized_question)
    return {
        "question": normalized_question,
        "context": [],
        "answer": "",
        "error": None,
        "route": (
            "invalid_question" if not normalized_question
            else "retrieve" if decision["source"] == "rag" else "incidents"
        ),
        "source": decision["source"],
        "incident_query": (
            decision["query"].model_dump() if decision["query"] is not None else None
        ),
        "incident_result": None,
    }


def route_question(state: AgentState) -> str:
    return state["route"]


def invalid_question(state: AgentState) -> ErrorUpdate:
    logger.warning("Agent question rejected reason=empty_question")
    return {"error": INVALID_QUESTION}


def retrieve_context(state: AgentState) -> ContextUpdate:
    context = pipeline.retrieve(state["question"])
    return {
        "context": context,
        "route": "generate" if context else "no_context",
    }


def route_context(state: AgentState) -> Literal["generate", "no_context"]:
    return state["route"]


def generate_response(state: AgentState) -> AnswerUpdate:
    question = state["question"]
    if state["source"] == "both":
        question = (
            "Responde exclusivamente la parte de políticas y procedimientos de esta "
            "pregunta. No afirmes ningún estado ni dato operativo de tickets: "
            + question
        )
    answer = pipeline.generate_answer(question, state["context"])
    if state["source"] == "both":
        answer = operational_answer(state) + "\n\nDocumentación:\n" + answer
    return {"answer": answer}


def no_context(state: AgentState) -> AnswerUpdate:
    prefix = operational_answer(state) + "\n\n" if state["source"] == "both" else ""
    return {"answer": prefix + NO_CONTEXT}


class IncidentUpdate(TypedDict):
    incident_result: IncidentResult
    route: Literal["retrieve", "incident_answer", "tool_fallback"]


def consult_incidents(state: AgentState) -> IncidentUpdate:
    query = state["incident_query"]
    result = (
        query_incidents(IncidentQuery.model_validate(query))
        if query is not None else failure("invalid_input")
    )
    return {
        "incident_result": result,
        "route": (
            "tool_fallback" if not result["ok"]
            else "retrieve" if state["source"] == "both" else "incident_answer"
        ),
    }


def route_incidents(state: AgentState) -> str:
    return state["route"]


def operational_answer(state: AgentState) -> str:
    result = state["incident_result"]
    if result is None:
        raise AgentGraphError("Incident response requested without a tool result.")
    if result["ok"]:
        return format_incidents(result)
    if result["error_code"] == "invalid_input":
        return FALLBACK + " Indica un único ID positivo o filtros no contradictorios."
    return FALLBACK


def incident_answer(state: AgentState) -> AnswerUpdate:
    return {"answer": operational_answer(state)}


class FallbackUpdate(AnswerUpdate):
    route: Literal["retrieve", "incident_answer"]


def tool_fallback(state: AgentState) -> FallbackUpdate:
    return {
        "answer": operational_answer(state),
        "route": "retrieve" if state["source"] == "both" else "incident_answer",
    }


def build_agent_graph() -> StateGraph[AgentState, None, AgentInput, AgentState]:
    builder = StateGraph(AgentState, input_schema=AgentInput)
    builder.add_node("receive", receive_question)
    builder.add_node("invalid_question", invalid_question)
    builder.add_node("retrieve", retrieve_context)
    builder.add_node("generate", generate_response)
    builder.add_node("no_context", no_context)
    builder.add_node("incidents", consult_incidents)
    builder.add_node("incident_answer", incident_answer)
    builder.add_node("tool_fallback", tool_fallback)
    builder.add_edge(START, "receive")
    builder.add_conditional_edges(
        "receive", route_question,
        {"retrieve": "retrieve", "incidents": "incidents", "invalid_question": "invalid_question"},
    )
    builder.add_conditional_edges(
        "retrieve", route_context,
        {"generate": "generate", "no_context": "no_context"},
    )
    builder.add_conditional_edges(
        "incidents", route_incidents,
        {"retrieve": "retrieve", "incident_answer": "incident_answer", "tool_fallback": "tool_fallback"},
    )
    builder.add_conditional_edges(
        "tool_fallback", route_incidents,
        {"retrieve": "retrieve", "incident_answer": "incident_answer"},
    )
    for node in ("invalid_question", "generate", "no_context", "incident_answer"):
        builder.add_edge(node, END)
    return builder


def _validate_structure(
    graph: CompiledStateGraph[AgentState, None, AgentInput, AgentState],
) -> None:
    structure = graph.get_graph()

    def reachable(start: str, *, reverse: bool = False) -> set[str]:
        visited: set[str] = set()
        pending = [start]
        while pending:
            node = pending.pop()
            if node in visited:
                continue
            visited.add(node)
            for edge in structure.edges:
                source, target = (
                    (edge.target, edge.source) if reverse else (edge.source, edge.target)
                )
                if source == node:
                    pending.append(target)
        return visited

    unreachable = set(structure.nodes) - reachable(START)
    unterminated = set(structure.nodes) - reachable(END, reverse=True)
    if unreachable or unterminated:
        raise AgentGraphError(
            "Invalid agent graph: "
            f"unreachable nodes={sorted(unreachable)}, "
            f"nodes without an END path={sorted(unterminated)}"
        )


def compile_agent_graph(
    checkpointer: SqliteSaver,
) -> CompiledStateGraph[AgentState, None, AgentInput, AgentState]:
    try:
        graph = build_agent_graph().compile(checkpointer=checkpointer)
    except ValueError as exc:
        raise AgentGraphError(f"Cannot compile agent graph: {exc}") from exc
    _validate_structure(graph)
    return graph


@contextmanager
def open_agent_graph(
    database_path: Path,
) -> Generator[CompiledStateGraph[AgentState, None, AgentInput, AgentState], None, None]:
    """Keep one compiled graph and its SQLite connection alive for the caller."""
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path, timeout=30, check_same_thread=False)
    try:
        checkpointer = SqliteSaver(connection)
        checkpointer.setup()
        yield compile_agent_graph(checkpointer)
    finally:
        connection.close()
