from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from incidents import CsvFormatError, analyze_incidents_csv
from routes.suppliers import router as suppliers_router

app = FastAPI(title="TrackFlow Incidents API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(suppliers_router)

_last_export_csv_bytes: bytes | None = None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/incidents/analyze")
async def analyze_incidents(file: UploadFile = File(...)) -> dict[str, Any]:
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
def export_last_result() -> StreamingResponse:
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
