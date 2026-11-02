"""Authenticated support-agent query and owner-scoped trace endpoints."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from auth import get_current_user
from services.support_agent.execution import AgentExecutionError, execute_agent
from services.support_agent.graph import CompiledStateGraph
from services.support_agent.traces import AgentTraceStore

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=2000)


class AgentQueryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str
    trace_id: str


class AgentErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    detail: str
    trace_id: str


def _agent_services(request: Request) -> tuple[
    CompiledStateGraph[Any, Any, Any, Any], AgentTraceStore
]:
    graph = getattr(request.app.state, "agent_graph", None)
    traces = getattr(request.app.state, "agent_traces", None)
    if graph is None or traces is None:
        raise HTTPException(
            status_code=503,
            detail="El agente no está disponible temporalmente.",
        )
    return graph, traces


@router.post(
    "/query",
    response_model=AgentQueryResponse,
    responses={422: {"model": AgentErrorResponse}, 503: {"model": AgentErrorResponse}},
)
def query_agent(
    request: AgentQueryRequest,
    http_request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> AgentQueryResponse | JSONResponse:
    graph, traces = _agent_services(http_request)
    try:
        execution = execute_agent(
            graph, traces, str(current_user["id"]), request.question
        )
    except AgentExecutionError as exc:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": "El agente no pudo completar la consulta.",
                "trace_id": exc.trace_id,
            },
        )
    if execution.error:
        return JSONResponse(
            status_code=422,
            content={"detail": execution.error, "trace_id": execution.trace_id},
        )
    return AgentQueryResponse(answer=execution.answer, trace_id=execution.trace_id)


@router.get("/traces/{trace_id}")
def get_agent_trace(
    trace_id: str,
    http_request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        trace_id = str(UUID(trace_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Trace no encontrado.") from exc
    _, traces = _agent_services(http_request)
    trace = traces.get_for_owner(trace_id, str(current_user["id"]))
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace no encontrado.")
    return trace
