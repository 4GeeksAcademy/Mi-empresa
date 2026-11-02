"""Streamable HTTP resource server: FastMCP tools, OAuth through MCP Auth."""

import json
import logging
import time
from typing import Annotated
from urllib.parse import urlsplit

import httpx
import uvicorn
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError, ValidationError as ToolValidationError
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools import ToolResult
from jwt import PyJWKClient
from mcp.types import CallToolRequestParams
from mcpauth import AuthInfo, AuthServerConfig, MCPAuth
from mcpauth.exceptions import (
    MCPAuthTokenVerificationException,
    MCPAuthTokenVerificationExceptionCode,
)
from mcpauth.utils import create_verify_jwt
from pydantic import Field, ValidationError
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.types import ASGIApp

from mcps.trackflow.backend import TrackFlowBackend
from mcps.trackflow.config import ServerSettings, validate_url
from services.api.incidents.models import IncidentCreate, IncidentFilters, IncidentResponse, IncidentStatusUpdate
from services.api.inventory_contracts import ProductResponse

logger = logging.getLogger("trackflow.mcp")
TOOL_SCOPES = {
    "list_incidents": "incidents:read",
    "get_incident": "incidents:read",
    "create_incident": "incidents:create",
    "update_incident_status": "incidents:update",
    "query_inventory": "inventory:read",
}
SCOPES = ["mcp:access", *sorted(set(TOOL_SCOPES.values()))]


class ToolPolicy(Middleware):
    def __init__(self, auth: MCPAuth) -> None:
        self.auth = auth

    async def on_call_tool(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        call_next: CallNext[CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        info = self.auth.auth_info
        name = context.message.name
        client = (info.client_id or info.subject) if info else "unauthenticated"
        outcome = "error"
        try:
            if info is None:
                raise ToolError("AUTHENTICATION_REQUIRED: a valid OAuth token is required.")
            if name not in TOOL_SCOPES:
                raise ToolError("TOOL_NOT_ALLOWED: unknown tools and inventory write tools are forbidden.")
            if TOOL_SCOPES[name] not in info.scopes:
                raise ToolError(f"INSUFFICIENT_SCOPE: this tool requires {TOOL_SCOPES[name]}.")
            if name == "query_inventory":
                arguments = context.message.arguments or {}
                if arguments.get("operation", "read") != "read":
                    raise ToolError("READ_ONLY_INVENTORY: only operation='read' is allowed; writes are forbidden.")
            result = await call_next(context)
            outcome = "success"
            return result
        except (ToolValidationError, ValidationError) as exc:
            raise ToolError("VALIDATION_ERROR: tool arguments do not match the advertised schema or allowed values.") from exc
        finally:
            logger.info("tool_invocation %s", json.dumps({
                "tool": name, "client": client, "result": outcome,
            }))


def create_tools(auth: MCPAuth, backend: TrackFlowBackend) -> FastMCP:
    mcp = FastMCP(
        "TrackFlow",
        instructions=(
            "Manage real TrackFlow incidents and read inventory. OAuth is mandatory. "
            "Each tool advertises its required scope. Inventory writes are forbidden, "
            "including attempts made with additional scopes. Incident status changes "
            "follow open -> in_progress/discarded; in_progress -> resolved/discarded."
        ),
        middleware=[ToolPolicy(auth)], strict_input_validation=True,
    )

    @mcp.tool(
        description=(
            "List real incidents. Requires incidents:read; no mutation. filters may be empty. "
            "status: open/in_progress/resolved/discarded; origin: customer/branch/internal; "
            "branch: los-angeles/zaragoza/central; "
            "category: logistica/tracking/devolucion/facturacion/soporte."
        ),
        annotations={"readOnlyHint": True}, meta={"required_scopes": ["incidents:read"]},
    )
    async def list_incidents(filters: IncidentFilters) -> list[IncidentResponse]:
        return await backend.list_incidents(filters)

    @mcp.tool(
        description="Read one real incident by its positive integer ticket ID. Returns status and original API fields. Requires incidents:read.",
        annotations={"readOnlyHint": True}, meta={"required_scopes": ["incidents:read"]},
    )
    async def get_incident(ticket_id: Annotated[int, Field(gt=0)]) -> IncidentResponse:
        return await backend.get_incident(ticket_id)

    @mcp.tool(
        description=(
            "Create an incident. Requires incidents:create. category: logistica/tracking/devolucion/facturacion/soporte; "
            "status: open/in_progress/resolved/discarded (default open); origin: customer/branch/internal; "
            "branch: los-angeles/zaragoza/central. Uses POST /api/incidents; not idempotent."
        ),
        annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False},
        meta={"required_scopes": ["incidents:create"]},
    )
    async def create_incident(incident: IncidentCreate) -> IncidentResponse:
        return await backend.create_incident(incident)

    @mcp.tool(
        description=(
            "Change incident status via PATCH /api/incidents/{id}/status. Requires incidents:update. "
            "Allowed transitions: open -> in_progress/discarded; in_progress -> resolved/discarded. "
            "resolved and discarded are terminal; the backend validates transitions."
        ),
        annotations={"readOnlyHint": False, "destructiveHint": True},
        meta={"required_scopes": ["incidents:update"]},
    )
    async def update_incident_status(
        ticket_id: Annotated[int, Field(gt=0)], update: IncidentStatusUpdate,
    ) -> IncidentResponse:
        return await backend.update_status(ticket_id, update)

    @mcp.tool(
        description=(
            "Read product stock, optionally by positive product_id. Requires inventory:read. "
            "Returns id/name/sku/warehouse/current_stock; warehouses are los_angeles or zaragoza. "
            "Only operation='read' is permitted. Every write operation is explicitly rejected; "
            "no inventory write scope is supported."
        ),
        annotations={"readOnlyHint": True},
        meta={"required_scopes": ["inventory:read"], "forbidden_operations": ["create", "update", "delete"]},
    )
    async def query_inventory(
        product_id: Annotated[int | None, Field(gt=0)] = None,
        operation: str = "read",
    ) -> list[ProductResponse]:
        if operation != "read":
            raise ToolError("READ_ONLY_INVENTORY: writes are forbidden.")
        return await backend.products(product_id)

    return mcp


class ResourceChallenge(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, metadata_url: str) -> None:
        super().__init__(app)
        self.metadata_url = metadata_url

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        if response.status_code in {401, 403}:
            error = "insufficient_scope" if response.status_code == 403 else "invalid_token"
            response.headers["WWW-Authenticate"] = (
                f'Bearer resource_metadata="{self.metadata_url}", error="{error}", scope="mcp:access"'
            )
        return response


def create_app(settings: ServerSettings | None = None) -> Starlette:
    settings = settings or ServerSettings.from_environment()
    discovery_url = settings.issuer.rstrip("/") + "/.well-known/openid-configuration"
    with httpx.Client(timeout=5.0, follow_redirects=False, trust_env=False) as client:
        response = client.get(discovery_url)
        response.raise_for_status()
        config = AuthServerConfig.model_validate({"metadata": response.json(), "type": "oidc"})
    if config.metadata.issuer != settings.issuer:
        raise ValueError("OIDC discovery issuer does not match TRACKFLOW_MCP_ISSUER.")
    if not config.metadata.jwks_uri:
        raise ValueError("OIDC discovery must provide jwks_uri.")
    validate_url(config.metadata.jwks_uri)
    auth = MCPAuth(server=config)
    verify_signature = create_verify_jwt(
        PyJWKClient(config.metadata.jwks_uri, timeout=5), leeway=0,
    )

    def verify_access_token(token: str) -> AuthInfo:
        info = verify_signature(token)
        expiry = info.claims.get("exp")
        if (
            not isinstance(expiry, (int, float))
            or isinstance(expiry, bool)
            or expiry <= time.time()
        ):
            raise MCPAuthTokenVerificationException(MCPAuthTokenVerificationExceptionCode.INVALID_TOKEN)
        return info

    origin = urlsplit(settings.resource_url)
    mcp = create_tools(auth, TrackFlowBackend(settings.backend_url))
    protected_app = mcp.http_app(
        path="/mcp", stateless_http=True,
        allowed_hosts=[origin.netloc],
        allowed_origins=settings.allowed_origins,
    )
    protected_app.add_middleware(auth.bearer_auth_middleware(
        verify_access_token, audience=settings.resource_url, required_scopes=["mcp:access"],
    ))
    metadata_url = f"{origin.scheme}://{origin.netloc}/.well-known/oauth-protected-resource/mcp"

    async def resource_metadata(request: Request) -> JSONResponse:
        return JSONResponse({
            "resource": settings.resource_url,
            "authorization_servers": [settings.issuer],
            "scopes_supported": SCOPES,
            "bearer_methods_supported": ["header"],
            "resource_name": "TrackFlow MCP",
        })

    app = Starlette(
        routes=[
            Route("/.well-known/oauth-protected-resource/mcp", resource_metadata),
            Route("/.well-known/oauth-protected-resource", resource_metadata),
            Mount("/", app=protected_app),
        ],
        lifespan=protected_app.lifespan,
    )
    app.add_middleware(ResourceChallenge, metadata_url=metadata_url)
    if settings.allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.allowed_origins,
            allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
            allow_headers=[
                "Authorization", "Content-Type", "Accept", "MCP-Protocol-Version",
                "Mcp-Session-Id", "Last-Event-ID",
            ],
            expose_headers=["WWW-Authenticate", "Mcp-Session-Id"],
        )
    return app


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = ServerSettings.from_environment()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port, access_log=False)


if __name__ == "__main__":
    main()
