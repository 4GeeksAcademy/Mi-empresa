"""Run one graph request and persist an ordered, resumable execution trace."""

import logging
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from langgraph.graph.state import CompiledStateGraph

from services.support_agent.graph import AgentInput, AgentState
from services.support_agent.memory import (
    AgentMemoryStore,
    MemoryResolution,
    propose_memory,
)
from services.support_agent.traces import AgentTraceStore

logger = logging.getLogger("trackflow_api.support_agent")


@dataclass(frozen=True)
class AgentExecution:
    trace_id: str
    answer: str
    error: str | None
    propuesta_memoria: dict[str, str] | None = None


class AgentExecutionError(RuntimeError):
    def __init__(self, trace_id: str) -> None:
        self.trace_id = trace_id
        super().__init__("Agent execution failed.")


def execute_agent(
    graph: CompiledStateGraph[Any, Any, Any, Any],
    traces: AgentTraceStore,
    owner_id: str,
    question: str,
    memory: AgentMemoryStore | None = None,
) -> AgentExecution:
    trace_id = str(uuid4())
    config = {"configurable": {"thread_id": trace_id}}
    resolution = (
        memory.resolve_pending(owner_id, question)
        if memory is not None
        else MemoryResolution("none", question.strip() or None)
    )
    graph_question = resolution.question
    proposal = resolution.proposal
    if graph_question is None:
        answer = _memory_decision_answer(resolution)
        traces.create(trace_id, owner_id, question)
        traces.finish(trace_id, status="completed", answer=answer)
        return AgentExecution(trace_id, answer, None, proposal)

    memory_context = (
        memory.relevant_memories(graph_question)
        if memory is not None
        else []
    )
    agent_input: AgentInput = {"question": graph_question}
    if memory_context:
        agent_input["memory_context"] = memory_context
    traces.create(trace_id, owner_id, question)
    try:
        for event in graph.stream(
            agent_input,
            config,
            stream_mode="tasks",
            durability="sync",
        ):
            node = event["name"]
            if "input" in event:
                traces.start_node(trace_id, node, event["input"])
            elif event.get("error") is not None:
                traces.fail_node(trace_id, node)
            elif "result" in event:
                traces.complete_node(trace_id, node, event["result"])
        state: AgentState = graph.get_state(config).values
        if state["error"]:
            traces.finish(trace_id, status="rejected", error_code="invalid_question")
            return AgentExecution(trace_id, answer="", error=state["error"])
        answer = state["answer"]
        if resolution.action == "approved":
            answer = "Propuesta aprobada y memoria actualizada.\n\n" + answer
        elif resolution.action == "rejected":
            answer = "Entendido; no guardaré la propuesta y la memoria no cambia.\n\n" + answer
        elif resolution.action == "unrelated":
            answer = "Descarté la propuesta pendiente al cambiar de tema.\n\n" + answer
        elif resolution.action == "expired":
            answer = (
                "La propuesta caducó tras 30 minutos sin confirmación; "
                "no se ha guardado y la memoria no cambia.\n\n" + answer
            )

        proposal_blocked = False
        if (
            memory is not None
            and proposal is None
            and resolution.action in {"none", "approved", "rejected", "unrelated"}
        ):
            draft = propose_memory(graph_question)
            if draft is not None:
                proposal = memory.propose(owner_id, draft)
                proposal_blocked = proposal is None
        if proposal is not None:
            answer += (
                "\n\nPropuesta de memoria: "
                f"{proposal['contenido']} {proposal['pregunta']}"
            )
        elif proposal_blocked:
            answer += (
                "\n\nNo he creado otra propuesta de memoria porque ya existe una "
                "pendiente de decisión. Resuélvela antes de proponer otra."
            )
        traces.finish(trace_id, status="completed", answer=answer)
        return AgentExecution(
            trace_id, answer=answer, error=None, propuesta_memoria=proposal,
        )
    except Exception as exc:
        logger.error(
            "Agent run failed trace_id=%s error_type=%s",
            trace_id,
            type(exc).__name__,
        )
        try:
            traces.finish(trace_id, status="failed", error_code="agent_error")
        except Exception as trace_exc:
            logger.error(
                "Agent failure trace persistence failed trace_id=%s error_type=%s",
                trace_id,
                type(trace_exc).__name__,
            )
        raise AgentExecutionError(trace_id) from exc


def _memory_decision_answer(resolution: MemoryResolution) -> str:
    if resolution.action == "approved":
        return "Propuesta aprobada y memoria actualizada."
    if resolution.action == "rejected":
        return "Entendido; no guardaré la propuesta y la memoria no cambia."
    if resolution.action == "edited":
        return (
            "He actualizado la propuesta, pero no la guardaré todavía. "
            "Revisa la propuesta_memoria y responde aprobar o rechazar."
        )
    if resolution.action == "ambiguous":
        return (
            "La propuesta sigue pendiente. Indica explícitamente si la apruebas, "
            "la rechazas o quieres editarla."
        )
    raise ValueError("No direct memory response is available for this action.")
