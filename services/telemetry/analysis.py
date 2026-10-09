from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd
from sqlmodel import Session, select

from database import get_engine
from models import TelemetryEventRecord


def _utc_database_boundary(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Report boundaries must include a timezone")
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _load_events(
    start_date: datetime,
    end_date: datetime,
    event_types: tuple[str, ...] | None = None,
    *,
    include_tags: bool = False,
) -> pd.DataFrame:
    columns = [TelemetryEventRecord.timestamp, TelemetryEventRecord.event_type]
    names = ["timestamp", "event_type"]
    if include_tags:
        columns.append(TelemetryEventRecord.tags)
        names.append("tags")

    statement = select(*columns).where(
        TelemetryEventRecord.timestamp >= _utc_database_boundary(start_date),
        TelemetryEventRecord.timestamp < _utc_database_boundary(end_date),
    )
    if event_types is not None:
        statement = statement.where(TelemetryEventRecord.event_type.in_(event_types))

    with Session(get_engine()) as session:
        rows = session.exec(statement).all()
    return pd.DataFrame(rows, columns=names)


def _add_utc_date(events: pd.DataFrame) -> pd.DataFrame:
    events = events.copy()
    events["timestamp"] = pd.to_datetime(events["timestamp"], utc=True)
    events["date"] = events["timestamp"].dt.strftime("%Y-%m-%d")
    return events


def _add_tag_fields(events: pd.DataFrame) -> pd.DataFrame:
    tags = pd.json_normalize(
        events["tags"].map(lambda value: value if isinstance(value, dict) else {}).tolist()
    )
    tags = tags.reindex(columns=["error_code", "route", "duration_ms"])
    return events.drop(columns="tags").join(tags)


def events_per_day(start_date: datetime, end_date: datetime) -> list[dict[str, Any]]:
    """Count stored events by UTC day and event type."""
    events = _load_events(start_date, end_date)
    if events.empty:
        return []

    events = _add_utc_date(events)
    report = events.groupby(["date", "event_type"], as_index=False).agg(
        event_count=("event_type", "count")
    )
    return report.to_dict(orient="records")


def error_rate_by_type(start_date: datetime, end_date: datetime) -> list[dict[str, Any]]:
    """Return observed API error rates by UTC day and normalized error code.

    The denominator is all ``api_latency_recorded`` events in that day. Since
    successful latency events are sampled, this is an observed telemetry rate,
    not an estimate of the full production request failure rate.
    """
    events = _load_events(
        start_date,
        end_date,
        ("api_error_recorded", "api_latency_recorded"),
        include_tags=True,
    )
    if events.empty:
        return []

    events = _add_utc_date(_add_tag_fields(events))
    errors = events.loc[
        events["event_type"].eq("api_error_recorded")
        & events["error_code"].notna()
        & events["error_code"].astype("string").str.strip().ne("")
    ]
    if errors.empty:
        return []

    error_counts = (
        errors.groupby(["date", "error_code"])
        .size()
        .rename("error_count")
        .reset_index()
    )
    observed_requests = (
        events.loc[events["event_type"].eq("api_latency_recorded")]
        .groupby("date")
        .size()
        .rename("observed_request_count")
        .reset_index()
    )
    report = error_counts.merge(observed_requests, on="date", how="inner")
    report["error_rate"] = report["error_count"] / report["observed_request_count"]
    return report.to_dict(orient="records")


def latency_by_endpoint(start_date: datetime, end_date: datetime) -> list[dict[str, Any]]:
    """Return mean observed API latency by UTC day and normalized route."""
    events = _load_events(
        start_date,
        end_date,
        ("api_latency_recorded",),
        include_tags=True,
    )
    if events.empty:
        return []

    events = _add_utc_date(_add_tag_fields(events))
    events["duration_ms"] = pd.to_numeric(events["duration_ms"], errors="coerce")
    events = events.loc[events["route"].notna() & events["duration_ms"].notna()]
    if events.empty:
        return []

    report = events.groupby(["date", "route"], as_index=False).agg(
        mean_latency_ms=("duration_ms", "mean"),
        sample_count=("duration_ms", "count"),
    )
    return report.to_dict(orient="records")