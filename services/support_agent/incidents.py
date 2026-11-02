"""Read incidents exclusively through authenticated MCP tools, with a total deadline."""

import asyncio
import logging
import os
from typing import Literal, TypedDict

import httpx
from langchain_core.messages import ToolMessage
from langchain_core.tools import ToolException
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools
from mcp import McpError
from pydantic import ConfigDict, Field, TypeAdapter

from services.api.service_urls import validate_url
from services.api.incidents.models import (
    ALLOWED_BRANCH_VALUES,
    ALLOWED_CATEGORIES_VALUES,
    ALLOWED_ORIGIN_VALUES,
    ALLOWED_STATUS_VALUES,
    IncidentFilters,
    IncidentResponse,
)

logger = logging.getLogger("trackflow_api.support_agent")
TIMEOUT_SECONDS = 5.0
FALLBACK = "No pude confirmar los datos de ese ticket o consulta ahora mismo."
ErrorCode = Literal[
    "timeout", "unavailable", "not_found", "authentication",
    "invalid_response", "invalid_input", "configuration", "http_error",
]


class IncidentQuery(IncidentFilters):
    model_config = ConfigDict(extra="forbid")

    ticket_id: int | None = Field(default=None, gt=0)


class IncidentSuccess(TypedDict):
    ok: Literal[True]
    incidents: list[dict[str, str | int]]


class IncidentFailure(TypedDict):
    ok: Literal[False]
    error_code: ErrorCode


IncidentResult = IncidentSuccess | IncidentFailure
INCIDENT_LIST = TypeAdapter(list[IncidentResponse])


def failure(code: ErrorCode) -> IncidentFailure:
    logger.warning("Incident tool failed reason=%s", code)
    return {"ok": False, "error_code": code}


def valid_filters(query: IncidentQuery) -> bool:
    return all(
        value is None or value in allowed
        for value, allowed in (
            (query.status, ALLOWED_STATUS_VALUES),
            (query.origin, ALLOWED_ORIGIN_VALUES),
            (query.branch, ALLOWED_BRANCH_VALUES),
            (query.category, ALLOWED_CATEGORIES_VALUES),
        )
    ) and not (
        query.ticket_id is not None
        and any((query.status, query.origin, query.branch, query.category))
    )


async def _get_incidents(query: IncidentQuery) -> IncidentResult:
    url = os.environ.get("TRACKFLOW_MCP_URL")
    token = os.environ.get("TRACKFLOW_MCP_TOKEN")
    if not url or not token:
        return failure("configuration")
    try:
        validate_url(url)
    except ValueError:
        return failure("configuration")
    client = MultiServerMCPClient({
        "trackflow": {
            "transport": "streamable_http",
            "url": url,
            "headers": {"Authorization": f"Bearer {token}"},
        },
    })
    name = "get_incident" if query.ticket_id is not None else "list_incidents"
    arguments = (
        {"ticket_id": query.ticket_id} if query.ticket_id is not None
        else {"filters": query.model_dump(exclude={"ticket_id"}, exclude_none=True)}
    )
    async with client.session("trackflow") as session:
        tools = await load_mcp_tools(session, handle_tool_errors=False)
        selected = next((tool for tool in tools if tool.name == name), None)
        if selected is None:
            return failure("configuration")
        result = await selected.ainvoke({
            "type": "tool_call", "name": name, "args": arguments, "id": "incident-query",
        })
    if not isinstance(result, ToolMessage) or not isinstance(result.artifact, dict):
        return failure("invalid_response")
    payload = result.artifact.get("structured_content")
    if not isinstance(payload, dict):
        return failure("invalid_response")
    try:
        records = INCIDENT_LIST.validate_python(
            [payload] if query.ticket_id is not None else payload.get("result"), strict=True,
        )
    except ValueError:
        return failure("invalid_response")
    if any(
        record.status not in ALLOWED_STATUS_VALUES
        or record.category not in ALLOWED_CATEGORIES_VALUES
        or record.origin not in ALLOWED_ORIGIN_VALUES
        or record.branch not in ALLOWED_BRANCH_VALUES
        for record in records
    ):
        return failure("invalid_response")
    if query.ticket_id is not None and records[0].id != query.ticket_id:
        return failure("invalid_response")
    return {"ok": True, "incidents": [record.model_dump() for record in records]}


def query_incidents(query: IncidentQuery) -> IncidentResult:
    if not valid_filters(query):
        return failure("invalid_input")
    try:
        return asyncio.run(asyncio.wait_for(_get_incidents(query), TIMEOUT_SECONDS))
    except (TimeoutError, httpx.HTTPError, McpError, ToolException) as exc:
        return failure(_error_code(exc))
    except ExceptionGroup as exc:
        handled, unhandled = exc.split((TimeoutError, httpx.HTTPError, McpError, ToolException))
        if unhandled is not None or handled is None:
            raise
        return failure(_error_code(handled))


def _error_code(error: Exception) -> ErrorCode:
    if isinstance(error, ExceptionGroup):
        codes: list[ErrorCode] = [_error_code(child) for child in error.exceptions]
        priority: tuple[ErrorCode, ...] = (
            "timeout", "authentication", "not_found", "invalid_input", "configuration",
        )
        for code in priority:
            if code in codes:
                return code
        return codes[0]
    if isinstance(error, (TimeoutError, httpx.TimeoutException)):
        return "timeout"
    if isinstance(error, httpx.HTTPStatusError):
        if error.response.status_code in {401, 403}:
            return "authentication"
        return "unavailable"
    if isinstance(error, ToolException):
        errors: dict[str, ErrorCode] = {
            "NOT_FOUND:": "not_found",
            "INSUFFICIENT_SCOPE:": "authentication",
            "AUTHENTICATION_REQUIRED:": "authentication",
            "BACKEND_AUTHENTICATION:": "authentication",
            "BACKEND_AUTHORIZATION:": "authentication",
            "VALIDATION_ERROR:": "invalid_input",
            "BACKEND_TIMEOUT:": "timeout",
            "INVALID_BACKEND_RESPONSE:": "invalid_response",
        }
        for marker, code in errors.items():
            if marker in str(error):
                return code
    return "unavailable"


def format_incidents(result: IncidentSuccess) -> str:
    if not result["incidents"]:
        return "No hay incidencias que coincidan con los filtros consultados."
    return "\n".join(
        f"Ticket {row['id']}: {row['title']}; estado: {row['status']}; "
        f"categoría: {row['category']}; origen: {row['origin']}; "
        f"sede: {row['branch']}; creado: {row['created_at']}; "
        f"actualizado: {row['updated_at']}. [gestor de incidentes]"
        for row in result["incidents"]
    )
