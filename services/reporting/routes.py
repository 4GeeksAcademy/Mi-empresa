from __future__ import annotations

import os
from datetime import date
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from prefect.deployments import run_deployment
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from auth import get_current_admin, get_current_user
from data.pipelines.pipeline import (
    get_pipeline_status,
    mark_scheduled_pipeline_run_failed,
    query_business_kpis,
    register_scheduled_pipeline_run,
    trackflow_business_performance_flow,
)

router = APIRouter(prefix="/reporting", tags=["reporting"])
MAX_WINDOW_DAYS = int(os.getenv("TRACKFLOW_REPORTING_MAX_WINDOW_DAYS", "31"))
STATUS_FIELDS = {
    "run_id",
    "flow_name",
    "trigger",
    "window_start",
    "window_end",
    "state",
    "started_at",
    "finished_at",
    "rows_read",
    "rows_written",
    "rows_rejected",
    "source_watermarks",
    "error_code",
    "error_message_safe",
}


def _require_reporting_role(current_user: dict[str, Any]) -> None:
    if current_user.get("role") not in {"admin", "manager"}:
        raise HTTPException(status_code=403, detail="Se requiere permiso de reporting.")


class PipelineRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    window_start: date
    window_end: date
    country_codes: list[str] = ["US", "ES"]

    @field_validator("country_codes")
    @classmethod
    def validate_countries(cls, value: list[str]) -> list[str]:
        if not value or len(value) != len(set(value)):
            raise ValueError("country_codes must be a non-empty unique list")
        if any(country not in {"US", "ES"} for country in value):
            raise ValueError("country_codes must contain only US and/or ES")
        return value

    @model_validator(mode="after")
    def validate_window(self) -> PipelineRunRequest:
        if self.window_start >= self.window_end:
            raise ValueError("window_start must be before window_end")
        if (self.window_end - self.window_start).days > MAX_WINDOW_DAYS:
            raise ValueError(f"window cannot exceed {MAX_WINDOW_DAYS} days")
        return self


@router.get("/pipeline/status")
def pipeline_status(
    run_id: str | None = None,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    _require_reporting_role(current_user)
    run = get_pipeline_status(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="No se encontró una ejecución del pipeline.")
    return {key: value for key, value in run.items() if key in STATUS_FIELDS}


@router.post("/pipeline/runs", status_code=status.HTTP_202_ACCEPTED)
async def trigger_pipeline_run(
    payload: PipelineRunRequest,
    current_user: dict[str, Any] = Depends(get_current_admin),
) -> dict[str, str]:
    deployment_name = os.getenv(
        "TRACKFLOW_REPORTING_DEPLOYMENT",
        f"{trackflow_business_performance_flow.name}/production",
    )
    run_id = str(uuid4())
    try:
        register_scheduled_pipeline_run(
            run_id,
            payload.window_start,
            payload.window_end,
            payload.country_codes,
            str(current_user["id"]),
        )
        run = await run_deployment(
            deployment_name,
            parameters={
                "window_start": payload.window_start.isoformat(),
                "window_end": payload.window_end.isoformat(),
                "country_codes": payload.country_codes,
                "trigger": "api",
                "requested_by": str(current_user["id"]),
                "run_id": run_id,
            },
            timeout=0,
            as_subflow=False,
            tags=["trackflow", "business-reporting"],
        )
    except Exception as exc:
        mark_scheduled_pipeline_run_failed(run_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo encolar el pipeline de reporting.",
        ) from exc
    return {"run_id": run_id, "state": "Scheduled"}


@router.get("/kpis")
def business_kpis(
    start_date: date,
    end_date: date,
    country_code: str | None = None,
    metric_codes: list[str] | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    _require_reporting_role(current_user)
    try:
        rows = query_business_kpis(start_date, end_date, country_code, metric_codes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    refreshed_at = max((row["refreshed_at"] for row in rows), default=None)
    return {
        "period": {"from": start_date.isoformat(), "to": end_date.isoformat(), "end_exclusive": True},
        "freshness": refreshed_at,
        "metrics": rows,
    }