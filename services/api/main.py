from __future__ import annotations

import csv
import io
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

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
from incidents import CsvFormatError, analyze_incidents_csv
from routes.auth import router as auth_router
from routes.incidents import router as incidents_router
from routes.inventory import router as inventory_router
from routes.profiles import router as profiles_router
from routes.suppliers import router as suppliers_router
from routes.users import router as users_router
from routes.telemetry import router as telemetry_router
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

_last_export_csv_bytes: bytes | None = None


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str


class IncidentAnalysisResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str
    summary: dict[str, object]


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/api/incidents/analyze", response_model=IncidentAnalysisResponse)
async def analyze_incidents(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
) -> IncidentAnalysisResponse:
    global _last_export_csv_bytes

    if not file.filename:
        raise HTTPException(status_code=400, detail="Debes adjuntar un fichero CSV.")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="El fichero CSV esta vacio.")

    try:
        csv_text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail="No se pudo decodificar el CSV. Usa UTF-8.",
        ) from exc

    try:
        result = analyze_incidents_csv(csv_text)
    except CsvFormatError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except csv.Error as exc:
        raise HTTPException(
            status_code=400,
            detail="El formato del CSV no es valido.",
        ) from exc

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["metric", "value"])
    for metric, value in result.to_metrics_rows():
        writer.writerow([metric, value])

    _last_export_csv_bytes = buffer.getvalue().encode("utf-8")

    return IncidentAnalysisResponse(
        filename=file.filename,
        summary=result.to_json(),
    )


@app.get("/api/incidents/results/export", response_model=None)
def export_last_result(
    current_user: dict = Depends(get_current_user),
) -> StreamingResponse:
    if _last_export_csv_bytes is None:
        raise HTTPException(
            status_code=404,
            detail="No hay resultados disponibles. Ejecuta primero /api/incidents/analyze.",
        )

    emit("report_exported", {"report_type": "incident_analysis", "format": "csv"})
    return StreamingResponse(
        io.BytesIO(_last_export_csv_bytes),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=results.csv"},
    )
