"""Allowlisted HTTP access to existing TrackFlow services."""

import logging
from typing import TypeVar

import httpx
from fastmcp.exceptions import ToolError
from pydantic import TypeAdapter, ValidationError

from services.api.incidents.models import (
    IncidentCreate,
    IncidentFilters,
    IncidentResponse,
    IncidentStatusUpdate,
)
from services.api.inventory_contracts import ProductResponse

logger = logging.getLogger("trackflow.mcp")
T = TypeVar("T")


class TrackFlowBackend:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    async def _request(
        self,
        method: str,
        path: str,
        response_type: TypeAdapter[T],
        *,
        params: dict[str, str] | None = None,
        payload: dict[str, str] | None = None,
    ) -> T:
        inventory_read = method == "GET" and (
            path == "/inventory/products"
            or (
                path.startswith("/inventory/products/")
                and path.removeprefix("/inventory/products/").isdigit()
            )
        )
        incident_id = path.removeprefix("/api/incidents/").removesuffix("/status")
        incident_allowed = (
            (path == "/api/incidents" and method in {"GET", "POST"})
            or (incident_id.isdigit() and method == "GET" and path == f"/api/incidents/{incident_id}")
            or (incident_id.isdigit() and method == "PATCH" and path == f"/api/incidents/{incident_id}/status")
        )
        if not (inventory_read or incident_allowed):
            raise ToolError("READ_ONLY_INVENTORY: inventory writes and arbitrary backend routes are forbidden.")
        try:
            async with httpx.AsyncClient(
                timeout=5.0, follow_redirects=False, trust_env=False,
            ) as client:
                response = await client.request(
                    method, self.base_url + path, params=params, json=payload,
                )
        except httpx.TimeoutException as exc:
            raise ToolError("BACKEND_TIMEOUT: backend did not respond in time.") from exc
        except httpx.RequestError as exc:
            raise ToolError("BACKEND_UNAVAILABLE: backend connection failed.") from exc
        if response.status_code >= 400:
            code = {
                400: "VALIDATION_ERROR", 401: "BACKEND_AUTHENTICATION",
                403: "BACKEND_AUTHORIZATION", 404: "NOT_FOUND", 422: "VALIDATION_ERROR",
            }.get(response.status_code, "BACKEND_UNAVAILABLE")
            logger.warning("backend_failure status=%s code=%s", response.status_code, code)
            raise ToolError(f"{code}: backend rejected the operation (HTTP {response.status_code}).")
        if response.status_code not in {200, 201}:
            raise ToolError("INVALID_BACKEND_RESPONSE: unexpected HTTP status.")
        try:
            return response_type.validate_python(response.json())
        except (ValueError, ValidationError) as exc:
            raise ToolError("INVALID_BACKEND_RESPONSE: response does not match the service contract.") from exc

    async def list_incidents(self, filters: IncidentFilters) -> list[IncidentResponse]:
        return await self._request(
            "GET", "/api/incidents", TypeAdapter(list[IncidentResponse]),
            params=filters.model_dump(exclude_none=True),
        )

    async def get_incident(self, ticket_id: int) -> IncidentResponse:
        return await self._request("GET", f"/api/incidents/{ticket_id}", TypeAdapter(IncidentResponse))

    async def create_incident(self, incident: IncidentCreate) -> IncidentResponse:
        return await self._request(
            "POST", "/api/incidents", TypeAdapter(IncidentResponse), payload=incident.model_dump(),
        )

    async def update_status(self, ticket_id: int, update: IncidentStatusUpdate) -> IncidentResponse:
        return await self._request(
            "PATCH", f"/api/incidents/{ticket_id}/status", TypeAdapter(IncidentResponse),
            payload=update.model_dump(),
        )

    async def products(self, product_id: int | None) -> list[ProductResponse]:
        if product_id is not None:
            return [await self._request("GET", f"/inventory/products/{product_id}", TypeAdapter(ProductResponse))]
        return await self._request("GET", "/inventory/products", TypeAdapter(list[ProductResponse]))
