from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from cache import TTLCache
from services.telemetry.analysis import (
    error_rate_by_type,
    events_per_day,
    latency_by_endpoint,
)
from telemetry import TelemetryBatch, TelemetryEvent as TelemetryEventModel, receive

router = APIRouter(prefix="/telemetry", tags=["telemetry"])
report_cache: TTLCache[dict[str, Any]] = TTLCache()
REPORT_CACHE_TTL_SECONDS = 60


@router.post("/events")
def receive_events(batch: TelemetryBatch) -> dict[str, int]:
    valid_events: list[TelemetryEventModel] = []
    rejected = 0
    for raw_event in batch.events:
        try:
            valid_events.append(TelemetryEventModel.model_validate(raw_event))
        except ValidationError:
            rejected += 1

    if valid_events:
        try:
            stored = receive(valid_events)
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Telemetry persistence failed") from exc
    else:
        stored = 0

    rejected += len(valid_events) - stored

    return {
        "received": len(batch.events),
        "stored": stored,
        "rejected": rejected,
    }


def _resolve_report_period(
    start_date: datetime | None,
    end_date: datetime | None,
) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    resolved_end = end_date or now
    resolved_start = start_date or resolved_end - timedelta(days=7)

    if resolved_start.tzinfo is None or resolved_start.utcoffset() is None:
        raise HTTPException(status_code=422, detail="start_date must include a timezone")
    if resolved_end.tzinfo is None or resolved_end.utcoffset() is None:
        raise HTTPException(status_code=422, detail="end_date must include a timezone")

    resolved_start = resolved_start.astimezone(timezone.utc)
    resolved_end = resolved_end.astimezone(timezone.utc)
    if resolved_start >= resolved_end:
        raise HTTPException(status_code=422, detail="start_date must be before end_date")
    return resolved_start, resolved_end


@router.get("/report")
def telemetry_report(
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> dict[str, Any]:
    period_start, period_end = _resolve_report_period(start_date, end_date)
    cache_key = "telemetry-report:" + ":".join(
        (
            start_date.astimezone(timezone.utc).isoformat() if start_date else "default-start-7d",
            end_date.astimezone(timezone.utc).isoformat() if end_date else "default-end-now",
        )
    )
    cached_report = report_cache.get(cache_key)
    if cached_report is not None:
        return cached_report

    report = {
        "period": {"from": period_start.isoformat(), "to": period_end.isoformat()},
        "metrics": {
            "events_per_day": events_per_day(period_start, period_end),
            "error_rate_by_type": error_rate_by_type(period_start, period_end),
            "latency_by_endpoint": latency_by_endpoint(period_start, period_end),
        },
    }
    report_cache.set(cache_key, report, ttl_seconds=REPORT_CACHE_TTL_SECONDS)
    return report