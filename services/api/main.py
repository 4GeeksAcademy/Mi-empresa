from __future__ import annotations

import io
import json
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exception_handlers import http_exception_handler
from starlette.exceptions import HTTPException as StarletteHTTPException
import re
from telemetry import TelemetryMiddleware, context, emit, normalized_route

from auth import get_current_user
from database import init_inventory_db
from kombu.exceptions import OperationalError
from redis.exceptions import RedisError
from services.celery_app import app as celery_app
from services.incident_tasks import analyze_incidents_task
from services import task_store
from routes.auth import router as auth_router
from routes.incidents import router as incidents_router
from routes.inventory import router as inventory_router
from routes.profiles import router as profiles_router
from routes.suppliers import router as suppliers_router
from routes.users import router as users_router
from routes.telemetry import router as telemetry_router
from services.reporting.routes import router as reporting_router
from pydantic import BaseModel, ConfigDict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("trackflow_api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_inventory_db()
    yield


app = FastAPI(title="TrackFlow Incidents API", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def timing_middleware(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - started) * 1000
    logger.info(
        "%s %s %s | %.1fms requestId=%s",
        request.method,
        normalized_route(request.url.path),
        response.status_code,
        duration_ms,
        (context.get() or {}).get("requestId", "none"),
    )
    response.headers["X-Response-Time-Ms"] = f"{duration_ms:.1f}"
    return response

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=getattr(exc, "headers", None))
    logger.error(
        "Unhandled exception method=%s route=%s requestId=%s type=%s",
        request.method,
        normalized_route(request.url.path),
        (context.get() or {}).get("requestId", "none"),
        type(exc).__name__,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Error interno del servidor. Intentalo de nuevo mas tarde."},
    )


@app.exception_handler(StarletteHTTPException)
async def telemetry_http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
):
    is_product_write = (
        request.method in {"PUT", "PATCH", "DELETE"}
        and re.fullmatch(r"/inventory/products(?:/[0-9]+)?", request.url.path)
    )
    if is_product_write:
        emit(
            "direct_stock_edit_rejected",
            {
                "resource": "inventory_product",
                "reason_code": "direct_stock_forbidden",
                "http_status": exc.status_code,
            },
        )
    return await http_exception_handler(request, exc)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TelemetryMiddleware, exception_handler=unhandled_exception_handler)


@app.exception_handler(RequestValidationError)
async def telemetry_validation_handler(request: Request, exc: RequestValidationError):
    if request.url.path.startswith("/telemetry/"):
        return JSONResponse(status_code=422, content={"detail": "Invalid telemetry batch"})
    if request.url.path.startswith("/inventory/"):
        operation = {"/inventory/products": "product_create", "/inventory/orders/inbound": "inbound_order", "/inventory/orders/outbound": "outbound_order"}.get(request.url.path, "inventory_request")
        emit("inventory_validation_failed", {"operation": operation, "reason_code": "invalid_input"})
        if any(error.get("type") == "extra_forbidden" and error["loc"][-1] in {"stock", "current_stock"} for error in exc.errors()):
            emit("direct_stock_edit_rejected", {"resource": "inventory_product", "reason_code": "direct_stock_forbidden", "http_status": 422})
    return await request_validation_exception_handler(request, exc)

app.include_router(incidents_router)
app.include_router(suppliers_router)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(profiles_router)
app.include_router(inventory_router)
app.include_router(telemetry_router)
app.include_router(reporting_router)

class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str


class TaskAcceptedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str


class TaskStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    status: Literal["pending", "started", "success", "failure"]
    result: dict | None = None


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/api/incidents/analyze", response_model=TaskAcceptedResponse, status_code=202)
def analyze_incidents(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
) -> TaskAcceptedResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Debes adjuntar un fichero CSV.")

    task_id = str(uuid4())
    try:
        task_store.create_upload(task_id, str(current_user["id"]), file.filename, file.file)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        analyze_incidents_task.apply_async(args=[task_id], task_id=task_id)
    except (OperationalError, RedisError, OSError) as exc:
        logger.error("task_id=%s state=publish_unknown error_type=%s", task_id, type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail={"task_id": task_id, "message": "No se pudo confirmar el encolado."},
        ) from exc
    return TaskAcceptedResponse(task_id=task_id)


@app.get("/tasks/{task_id}", response_model=TaskStatusResponse)
def task_status(
    task_id: UUID,
    current_user: dict = Depends(get_current_user),
) -> TaskStatusResponse:
    identifier = str(task_id)
    job = task_store.get_job(identifier)
    if job is None or job["owner"] != str(current_user["id"]):
        raise HTTPException(status_code=404, detail="Tarea no encontrada.")
    if job["result"] is not None:
        return TaskStatusResponse(task_id=identifier, status="success", result=json.loads(job["result"]))
    if task_store.get_failure(identifier):
        return TaskStatusResponse(task_id=identifier, status="failure")
    try:
        result = celery_app.AsyncResult(identifier)
        state = result.state
        status = {
            "PENDING": "pending", "RECEIVED": "pending", "RETRY": "pending",
            "STARTED": "started", "SUCCESS": "success", "FAILURE": "failure",
            "REVOKED": "failure",
        }.get(state, "pending")
        payload = result.result if state == "SUCCESS" else None
    except (RedisError, OperationalError) as exc:
        raise HTTPException(status_code=503, detail="Estado temporalmente no disponible.") from exc
    return TaskStatusResponse(task_id=identifier, status=status, result=payload)


@app.get("/api/incidents/results/export", response_model=None)
def export_last_result(
    current_user: dict = Depends(get_current_user),
) -> StreamingResponse:
    export = task_store.latest_export()
    if export is None:
        raise HTTPException(
            status_code=404,
            detail="No hay resultados disponibles. Ejecuta primero /api/incidents/analyze.",
        )

    emit("report_exported", {"report_type": "incident_analysis", "format": "csv"})
    return StreamingResponse(
        io.BytesIO(export),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=results.csv"},
    )
