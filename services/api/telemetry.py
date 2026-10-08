from __future__ import annotations

import json
import logging
import os
import re
import time
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlmodel import Session
from starlette.requests import Request
from starlette.responses import JSONResponse
from dotenv import load_dotenv

from database import get_engine
from models import TelemetryEventRecord

load_dotenv()
CONTRACT_DIR = Path(__file__).resolve().parents[2] / "docs" / "telemetry"
CATALOG = json.loads((CONTRACT_DIR / "event-schemas.json").read_text())
RULES = json.loads((CONTRACT_DIR / "runtime-rules.json").read_text())
EVENTS = {event["event_type"]: event for event in CATALOG["events"]}
if len(EVENTS) != len(CATALOG["events"]):
    raise RuntimeError("Duplicate telemetry event types")
SERVICE_NAMES = {"frontend": "backoffice", "backend": "api"}
TELEMETRY_ENDPOINT = os.getenv("TELEMETRY_ENDPOINT", "http://localhost:8000/telemetry/events")
logger = logging.getLogger("trackflow.telemetry")
context: ContextVar[dict[str, Any] | None] = ContextVar("telemetry_context", default=None)


def correlation_id(value: str | None) -> str:
    try:
        return str(UUID(value)) if value else str(uuid4())
    except ValueError:
        return str(uuid4())


def normalized_route(value: str) -> str:
    path = value.split("?", 1)[0].split("#", 1)[0]
    for template in RULES["routes"]:
        pattern = re.sub(r"\\\{[^}]+\\\}", r"[0-9]+", re.escape(template))
        if re.fullmatch(pattern, path):
            return template
    return "/unknown"


def validate_properties(event_type: str, properties: dict[str, Any]) -> dict[str, Any]:
    event = EVENTS.get(event_type)
    if event is None or not set(properties).issubset(event["allowlist"]):
        raise ValueError("Unknown event or property")
    result = dict(properties)
    for prop in event["properties"]:
        name = prop["name"]
        if name not in result:
            if prop["required"]:
                raise ValueError("Missing required property")
            continue
        value = result[name]
        if prop["type"] == "integer":
            minimum = 1 if name in RULES["positiveIntegers"] else 0
            if type(value) is not int or not minimum <= value <= RULES["maxInteger"]:
                raise ValueError("Invalid numeric property")
            if name in {"http_status", "status_code"} and not 100 <= value <= 599:
                raise ValueError("Invalid HTTP status")
        elif prop["type"] == "string":
            if not isinstance(value, str):
                raise ValueError("Invalid string property")
            if name == "route":
                value = normalized_route(value)
            elif name == "sku":
                value = value.strip().upper()
                if not re.fullmatch(r"[A-Z0-9][A-Z0-9._-]{0,63}", value):
                    raise ValueError("Invalid technical SKU")
            allowed = prop.get("allowed_values") or RULES["eventValues"].get(event_type, {}).get(name) or RULES["values"].get(name)
            if allowed is not None and value not in allowed:
                raise ValueError("Invalid controlled value")
            if allowed is None and name not in {"route", "sku"}:
                raise ValueError("Missing controlled value rule")
            result[name] = value
        else:
            raise ValueError("Unsupported property type")
    return result


class TelemetryEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    eventId: str
    timestamp: str
    sessionId: str | None
    userId: str | None
    event_type: str
    schemaVersion: str
    requestId: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    properties: dict[str, Any]

    @field_validator("eventId", "sessionId", "requestId")
    @classmethod
    def valid_uuid(cls, value: str | None) -> str | None:
        if value is not None:
            UUID(value)
        return value

    @field_validator("userId")
    @classmethod
    def valid_user(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"[1-9][0-9]*|[0-9a-fA-F-]{36}", value):
            raise ValueError("Invalid internal user identifier")
        return value

    @field_validator("timestamp")
    @classmethod
    def valid_time(cls, value: str) -> str:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
            raise ValueError("UTC timestamp required")
        return value

    @model_validator(mode="after")
    def valid_contract(self) -> TelemetryEvent:
        if self.schemaVersion != RULES["schemaVersion"]:
            raise ValueError("Unsupported schema version")
        self.properties = validate_properties(self.event_type, self.properties)
        return self


class TelemetryBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    events: list[Any] = Field(max_length=100)


def receive(events: list[TelemetryEvent]) -> int:
    if not events:
        return 0

    with Session(get_engine()) as session:
        try:
            rows = [
                {
                    "id": UUID(event.eventId),
                    "timestamp": datetime.fromisoformat(event.timestamp.replace("Z", "+00:00")),
                    "service": SERVICE_NAMES[EVENTS[event.event_type]["producer"]],
                    "event_type": event.event_type,
                    "level": "info",
                    "value": None,
                    "message": None,
                    "tags": {
                        **event.properties,
                        "sessionId": event.sessionId,
                        "userId": event.userId,
                        "schemaVersion": event.schemaVersion,
                        "requestId": event.requestId,
                    },
                }
                for event in events
            ]
            dialect = session.get_bind().dialect.name
            if dialect == "postgresql":
                insert = postgresql_insert(TelemetryEventRecord.__table__)
            elif dialect == "sqlite":
                insert = sqlite_insert(TelemetryEventRecord.__table__)
            else:
                raise RuntimeError("Unsupported telemetry database dialect")
            result = session.execute(
                insert.values(rows).on_conflict_do_nothing(index_elements=["id"])
            )
            session.commit()
            stored = result.rowcount or 0
        except Exception:
            session.rollback()
            raise
    logger.info("received=%s stored=%s", len(events), stored)
    return stored


def emit(event_type: str, properties: dict[str, Any], user_id: str | None = None) -> None:
    try:
        if EVENTS[event_type]["producer"] != "backend":
            return
        state = context.get() or {}
        event = TelemetryEvent(
            eventId=str(uuid4()), timestamp=datetime.now(timezone.utc).isoformat(),
            sessionId=state.get("sessionId"), userId=user_id or state.get("userId"),
            event_type=event_type, schemaVersion=RULES["schemaVersion"],
            requestId=state.get("requestId", str(uuid4())), properties=properties,
        )
        if "events" in state:
            state["events"].append(event)
        else:
            receive([event])
    except Exception:
        logger.warning("telemetry_event_discarded")


def stock_threshold() -> int:
    try:
        value = int(os.getenv("TELEMETRY_STOCK_THRESHOLD", "10"))
        return value if 0 < value <= RULES["maxInteger"] else 10
    except ValueError:
        return 10


class TelemetryMiddleware:
    def __init__(self, app, exception_handler=None):
        self.app = app
        self.exception_handler = exception_handler
        self.latency_windows: dict[tuple[str | None, str], float] = {}

    async def __call__(self, scope, receive_request, send):
        if scope["type"] != "http" or scope["path"].startswith("/telemetry/"):
            await self.app(scope, receive_request, send)
            return
        headers = dict(scope.get("headers", []))
        session = headers.get(b"x-session-id", b"").decode("ascii", errors="ignore")
        try:
            session = str(UUID(session)) if session else None
        except ValueError:
            session = None
        state = {
            "requestId": correlation_id(headers.get(b"x-request-id", b"").decode("ascii", errors="ignore")),
            "sessionId": session, "userId": None, "events": [],
            "route": normalized_route(scope["path"]),
        }
        token = context.set(state)
        started = time.perf_counter()
        status_code = 500
        completed = False
        response_started = False

        async def send_response(message):
            nonlocal status_code, completed, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]
                message["headers"] = list(message.get("headers", [])) + [(b"x-request-id", state["requestId"].encode())]
            await send(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                completed = True

        try:
            await self.app(scope, receive_request, send_response)
        except Exception as exc:
            if response_started:
                raise
            if self.exception_handler is not None:
                response = await self.exception_handler(Request(scope), exc)
            else:
                response = JSONResponse(status_code=500, content={"detail": "Internal server error"})
            await response(scope, receive_request, send_response)
        finally:
            if completed:
                route = state["route"]
                method = scope["method"]
                if method in RULES["values"]["method"]:
                    props = {"route": route, "method": method, "status_code": status_code}
                    now = time.monotonic()
                    key = (session, route)
                    if status_code >= 400 or now - self.latency_windows.get(key, -10) >= 10:
                        emit("api_latency_recorded", {**props, "duration_ms": max(0, round((time.perf_counter() - started) * 1000))})
                        if len(self.latency_windows) >= 10000:
                            self.latency_windows.clear()
                        self.latency_windows[key] = now
                    if status_code >= 400:
                        code = {401: "unauthorized", 403: "forbidden", 404: "not_found", 422: "validation_error"}.get(status_code, "server_error" if status_code >= 500 else "request_rejected")
                        emit("api_error_recorded", {**props, "error_code": code})
                try:
                    receive(state["events"])
                except Exception:
                    logger.warning("telemetry_batch_discarded")
            context.reset(token)