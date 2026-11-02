"""Read live incidents through the existing backend, with a total deadline."""

import asyncio
import logging
import os
from typing import Literal, TypedDict

import httpx
from pydantic import ConfigDict, Field, TypeAdapter

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
    base_url = os.environ.get("TRACKFLOW_INCIDENTS_BASE_URL", "http://localhost:8000")
    url = httpx.URL(base_url)
    if url.scheme not in {"http", "https"} or not url.host or url.userinfo or url.query or url.fragment:
        return failure("configuration")
    token = os.environ.get("TRACKFLOW_INCIDENTS_TOKEN")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    path = "/api/incidents"
    if query.ticket_id is not None:
        path += f"/{query.ticket_id}"
    params = query.model_dump(exclude={"ticket_id"}, exclude_none=True)
    async with httpx.AsyncClient(
        timeout=TIMEOUT_SECONDS, follow_redirects=False, trust_env=False,
    ) as client:
        response = await client.get(
            str(url).rstrip("/") + path, params=params, headers=headers,
        )
    if response.status_code in {401, 403}:
        return failure("authentication")
    if response.status_code == 404:
        return failure("not_found")
    if response.status_code >= 500:
        return failure("unavailable")
    if response.status_code != 200:
        return failure("http_error")
    try:
        payload = response.json()
        records = INCIDENT_LIST.validate_python(
            [payload] if query.ticket_id is not None else payload, strict=True,
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
    except (TimeoutError, httpx.TimeoutException):
        return failure("timeout")
    except httpx.InvalidURL:
        return failure("configuration")
    except httpx.RequestError:
        return failure("unavailable")


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
