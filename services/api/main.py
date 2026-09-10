from __future__ import annotations

import csv
import io
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from auth import get_current_user
from database import init_inventory_db
from incidents import CsvFormatError, analyze_incidents_csv
from routes.auth import router as auth_router
from routes.incidents import router as incidents_router
from routes.inventory import router as inventory_router
from routes.profiles import router as profiles_router
from routes.suppliers import router as suppliers_router
from routes.users import router as users_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("trackflow_api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_inventory_db()
    yield


app = FastAPI(title="TrackFlow Incidents API", version="1.0.0", lifespan=lifespan)

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=getattr(exc, "headers", None))
    logger.error("Excepcion no controlada en %s %s: %s", request.method, request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Error interno del servidor. Intentalo de nuevo mas tarde."},
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(incidents_router)
app.include_router(suppliers_router)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(profiles_router)
app.include_router(inventory_router)

_last_export_csv_bytes: bytes | None = None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/incidents/analyze")
async def analyze_incidents(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
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

    return {
        "filename": file.filename,
        "summary": result.to_json(),
    }


@app.get("/api/incidents/results/export")
def export_last_result(
    current_user: dict = Depends(get_current_user),
) -> StreamingResponse:
    if _last_export_csv_bytes is None:
        raise HTTPException(
            status_code=404,
            detail="No hay resultados disponibles. Ejecuta primero /api/incidents/analyze.",
        )

    return StreamingResponse(
        io.BytesIO(_last_export_csv_bytes),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=results.csv"},
    )
