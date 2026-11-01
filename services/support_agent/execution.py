"""Run one graph request and persist an ordered, resumable execution trace."""

import logging
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from langgraph.graph.state import CompiledStateGraph

from services.support_agent.graph import AgentInput, AgentState
from services.support_agent.traces import AgentTraceStore

logger = logging.getLogger("trackflow_api.support_agent")


@dataclass(frozen=True)
class AgentExecution:
    trace_id: str
    answer: str
    error: str | None


class AgentExecutionError(RuntimeError):
    def __init__(self, trace_id: str) -> None:
        self.trace_id = trace_id
        super().__init__("Agent execution failed.")


def execute_agent(
    graph: CompiledStateGraph[Any, Any, Any, Any],
    traces: AgentTraceStore,
    owner_id: str,
    question: str,
) -> AgentExecution:
    trace_id = str(uuid4())
    config = {"configurable": {"thread_id": trace_id}}
    agent_input: AgentInput = {"question": question}
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
        traces.finish(trace_id, status="completed", answer=state["answer"])
        return AgentExecution(trace_id, answer=state["answer"], error=None)
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
