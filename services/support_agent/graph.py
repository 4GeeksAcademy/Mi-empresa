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
    route: Literal["retrieve", "invalid_question", "generate", "no_context"]


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
    return {
        "question": normalized_question,
        "context": [],
        "answer": "",
        "error": None,
        "route": "retrieve" if normalized_question else "invalid_question",
    }


def route_question(state: AgentState) -> Literal["retrieve", "invalid_question"]:
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
    return {"answer": pipeline.generate_answer(state["question"], state["context"])}


def no_context(state: AgentState) -> AnswerUpdate:
    return {"answer": NO_CONTEXT}


def build_agent_graph() -> StateGraph[AgentState, None, AgentInput, AgentState]:
    builder = StateGraph(AgentState, input_schema=AgentInput)
    builder.add_node("receive", receive_question)
    builder.add_node("invalid_question", invalid_question)
    builder.add_node("retrieve", retrieve_context)
    builder.add_node("generate", generate_response)
    builder.add_node("no_context", no_context)
    builder.add_edge(START, "receive")
    builder.add_conditional_edges(
        "receive", route_question,
        {"retrieve": "retrieve", "invalid_question": "invalid_question"},
    )
    builder.add_conditional_edges(
        "retrieve", route_context,
        {"generate": "generate", "no_context": "no_context"},
    )
    for node in ("invalid_question", "generate", "no_context"):
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
