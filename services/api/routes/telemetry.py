from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from telemetry import TelemetryBatch, TelemetryEvent as TelemetryEventModel, receive

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


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