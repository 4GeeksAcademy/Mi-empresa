from fastapi import APIRouter

from telemetry import TelemetryBatch, receive

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


@router.post("/events")
def receive_events(batch: TelemetryBatch) -> dict[str, int]:
    receive(batch.events)
    return {"received": len(batch.events)}