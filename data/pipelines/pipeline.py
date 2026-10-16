from __future__ import annotations

import os
import sys
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))
load_dotenv(REPOSITORY_ROOT / ".env")
os.environ.setdefault("PREFECT_SERVER_ANALYTICS_ENABLED", "false")

from prefect import flow, task
from prefect.tasks import task_input_hash
from sqlalchemy import (
    JSON,
    Column,
    Date,
    DateTime,
    Index,
    Integer,
    MetaData,
    Numeric,
    SmallInteger,
    String,
    Table,
    Uuid,
    and_,
    create_engine,
    delete,
    insert,
    inspect,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine

from data.process.business_kpis import calculate_business_kpis

FLOW_NAME = "trackflow_business_performance_flow"
SCHEMA = "reporting"
DB_RETRIES = 2
DB_RETRY_DELAY_SECONDS = 2
DEFINITION_VERSION = 1
LEASE_DURATION = timedelta(minutes=5)
JSON_TYPE = JSON().with_variant(JSONB, "postgresql")
metadata = MetaData()

pipeline_runs = Table(
    "pipeline_runs", metadata,
    Column("run_id", Uuid(as_uuid=False), primary_key=True),
    Column("flow_name", String(120), nullable=False),
    Column("trigger", String(32), nullable=False),
    Column("requested_by", String(120)),
    Column("window_start", Date, nullable=False),
    Column("window_end", Date, nullable=False),
    Column("state", String(24), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True)),
    Column("rows_read", Integer, nullable=False, default=0),
    Column("rows_written", Integer, nullable=False, default=0),
    Column("rows_rejected", Integer, nullable=False, default=0),
    Column("source_watermarks", JSON_TYPE, nullable=False),
    Column("error_code", String(64)),
    Column("error_message_safe", String(240)),
    Column("request_id", Uuid(as_uuid=False)),
    schema=SCHEMA,
)
business_kpis_daily = Table(
    "business_kpis_daily", metadata,
    Column("metric_date", Date, primary_key=True),
    Column("country_code", String(2), primary_key=True),
    Column("metric_code", String(40), primary_key=True),
    Column("currency_code", String(3), primary_key=True),
    Column("metric_value", Numeric(20, 6), nullable=False),
    Column("numerator", Numeric(20, 6)),
    Column("denominator", Numeric(20, 6)),
    Column("unit", String(16), nullable=False),
    Column("source_watermark", DateTime(timezone=True), nullable=False),
    Column("refreshed_at", DateTime(timezone=True), nullable=False),
    Column("definition_version", SmallInteger, nullable=False),
    Column("run_id", Uuid(as_uuid=False), nullable=False),
    schema=SCHEMA,
)
Index("ix_business_kpis_country_date", business_kpis_daily.c.country_code, business_kpis_daily.c.metric_date)
Index("ix_business_kpis_metric_date", business_kpis_daily.c.metric_code, business_kpis_daily.c.metric_date)

business_kpi_staging = Table(
    "business_kpi_staging", metadata,
    Column("run_id", Uuid(as_uuid=False), primary_key=True),
    Column("metric_date", Date, primary_key=True),
    Column("country_code", String(2), primary_key=True),
    Column("metric_code", String(40), primary_key=True),
    Column("currency_code", String(3), primary_key=True),
    Column("metric_value", Numeric(20, 6), nullable=False),
    Column("numerator", Numeric(20, 6)),
    Column("denominator", Numeric(20, 6)),
    Column("unit", String(16), nullable=False),
    Column("source_watermark", DateTime(timezone=True), nullable=False),
    Column("refreshed_at", DateTime(timezone=True), nullable=False),
    Column("definition_version", SmallInteger, nullable=False),
    schema=SCHEMA,
)
pipeline_staging_partitions = Table(
    "pipeline_staging_partitions", metadata,
    Column("run_id", Uuid(as_uuid=False), primary_key=True),
    Column("metric_date", Date, primary_key=True),
    Column("country_code", String(2), primary_key=True),
    Column("source_watermark", DateTime(timezone=True), nullable=False),
    Column("state", String(24), nullable=False),
    schema=SCHEMA,
)
pipeline_checkpoints = Table(
    "pipeline_checkpoints", metadata,
    Column("source_name", String(100), primary_key=True),
    Column("country_code", String(2), primary_key=True),
    Column("cursor_timestamp", DateTime(timezone=True)),
    Column("cursor_id", String(160)),
    Column("committed_through", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("last_successful_run_id", Uuid(as_uuid=False), nullable=False),
    schema=SCHEMA,
)
pipeline_window_locks = Table(
    "pipeline_window_locks", metadata,
    Column("window_start", Date, primary_key=True),
    Column("window_end", Date, primary_key=True),
    Column("country_code", String(2), primary_key=True),
    Column("owner_run_id", Uuid(as_uuid=False), nullable=False),
    Column("lease_expires_at", DateTime(timezone=True), nullable=False),
    Column("heartbeat_at", DateTime(timezone=True), nullable=False),
    schema=SCHEMA,
)
pipeline_reprocess_queue = Table(
    "pipeline_reprocess_queue", metadata,
    Column("source_name", String(100), primary_key=True),
    Column("country_code", String(2), primary_key=True),
    Column("metric_date", Date, primary_key=True),
    Column("reason", String(240), nullable=False),
    Column("status", String(24), nullable=False),
    Column("requested_at", DateTime(timezone=True), nullable=False),
    Column("claimed_by_run_id", Uuid(as_uuid=False)),
    Column("completed_at", DateTime(timezone=True)),
    schema=SCHEMA,
)


@lru_cache(maxsize=1)
def get_reporting_engine() -> Engine:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        local_db = REPOSITORY_ROOT / "data" / "process" / "business_reporting.sqlite3"
        local_db.parent.mkdir(parents=True, exist_ok=True)
        database_url = f"sqlite:///{local_db}"
    engine = create_engine(database_url, pool_pre_ping=True)
    if engine.dialect.name == "sqlite":
        engine = engine.execution_options(schema_translate_map={SCHEMA: None})
    else:
        with engine.begin() as connection:
            connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))
    metadata.create_all(engine)
    return engine


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime):
        raise ValueError("Invalid timestamp")
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _validate_window(window_start: date, window_end: date, countries: list[str]) -> None:
    if window_start >= window_end:
        raise ValueError("window_start must be before window_end")
    if not countries or len(countries) != len(set(countries)) or any(country not in {"US", "ES"} for country in countries):
        raise ValueError("country_codes must be a unique non-empty subset of US and ES")


def register_scheduled_pipeline_run(run_id: str, window_start: date, window_end: date,
                                    country_codes: list[str], requested_by: str) -> None:
    _validate_window(window_start, window_end, country_codes)
    with get_reporting_engine().begin() as connection:
        connection.execute(insert(pipeline_runs).values(
            run_id=run_id, flow_name=FLOW_NAME, trigger="api", requested_by=requested_by,
            window_start=window_start, window_end=window_end, state="Scheduled", started_at=_now(),
            rows_read=0, rows_written=0, rows_rejected=0,
            source_watermarks={"business_sources": "not_configured"},
        ))


def mark_scheduled_pipeline_run_failed(run_id: str) -> None:
    with get_reporting_engine().begin() as connection:
        connection.execute(update(pipeline_runs).where(pipeline_runs.c.run_id == run_id).values(
            state="Failed", finished_at=_now(), error_code="PREFECT_ENQUEUE_FAILED",
            error_message_safe="No se pudo encolar el deployment Prefect.",
        ))


@task(retries=DB_RETRIES, retry_delay_seconds=DB_RETRY_DELAY_SECONDS)
def create_pipeline_run(run_id: str, window_start: date, window_end: date,
                        trigger: str, requested_by: str | None, started_at: datetime) -> None:
    # Two short retries absorb transient database errors without masking persistent failures.
    values = {
        "state": "Running", "started_at": started_at, "trigger": trigger,
        "requested_by": requested_by,
        "source_watermarks": {"telemetry_events": "observability_only", "business_sources": "not_configured"},
    }
    with get_reporting_engine().begin() as connection:
        result = connection.execute(update(pipeline_runs).where(pipeline_runs.c.run_id == run_id).values(**values))
        if result.rowcount == 0:
            connection.execute(insert(pipeline_runs).values(
                run_id=run_id, flow_name=FLOW_NAME, window_start=window_start, window_end=window_end,
                rows_read=0, rows_written=0, rows_rejected=0, **values,
            ))


@task(retries=DB_RETRIES, retry_delay_seconds=DB_RETRY_DELAY_SECONDS)
def acquire_window_locks(run_id: str, window_start: date, window_end: date,
                         country_codes: list[str]) -> bool:
    now = _now()
    expiry = now + LEASE_DURATION
    keys = [(window_start, window_end, country) for country in country_codes]
    with get_reporting_engine().begin() as connection:
        existing = {}
        for start, end, country in keys:
            key = and_(pipeline_window_locks.c.window_start == start,
                       pipeline_window_locks.c.window_end == end,
                       pipeline_window_locks.c.country_code == country)
            row = connection.execute(select(pipeline_window_locks).where(key).with_for_update()).first()
            existing[(start, end, country)] = row
            if row and row.owner_run_id != run_id and (_utc_datetime(row.lease_expires_at) or now) > now:
                return False
        for (start, end, country), row in existing.items():
            values = {"owner_run_id": run_id, "lease_expires_at": expiry, "heartbeat_at": now}
            key = and_(pipeline_window_locks.c.window_start == start,
                       pipeline_window_locks.c.window_end == end,
                       pipeline_window_locks.c.country_code == country)
            if row:
                connection.execute(update(pipeline_window_locks).where(key).values(**values))
            else:
                connection.execute(insert(pipeline_window_locks).values(
                    window_start=start, window_end=end, country_code=country, **values,
                ))
    return True


@task(retries=DB_RETRIES, retry_delay_seconds=DB_RETRY_DELAY_SECONDS)
def heartbeat_window_locks(run_id: str) -> None:
    now = _now()
    with get_reporting_engine().begin() as connection:
        connection.execute(update(pipeline_window_locks).where(
            pipeline_window_locks.c.owner_run_id == run_id
        ).values(heartbeat_at=now, lease_expires_at=now + LEASE_DURATION))


@task(retries=DB_RETRIES, retry_delay_seconds=DB_RETRY_DELAY_SECONDS)
def release_window_locks(run_id: str) -> None:
    with get_reporting_engine().begin() as connection:
        connection.execute(delete(pipeline_window_locks).where(pipeline_window_locks.c.owner_run_id == run_id))


@task(retries=DB_RETRIES, retry_delay_seconds=DB_RETRY_DELAY_SECONDS)
def extract_source_batch(window_start: date, window_end: date) -> dict[str, Any]:
    """Read telemetry only for reconciliation; it is never a business KPI source."""
    engine = get_reporting_engine()
    if not inspect(engine).has_table("telemetry_events"):
        return {"events": [], "telemetry_status": "unavailable", "telemetry_watermark": None,
                "business_watermark": None, "business_facts": {},
                "business_sources_complete": False, "source_cursors": {}}
    start_at = datetime.combine(window_start, time.min, tzinfo=timezone.utc).replace(tzinfo=None)
    end_at = datetime.combine(window_end, time.min, tzinfo=timezone.utc).replace(tzinfo=None)
    with engine.connect() as connection:
        results = connection.execute(text(
            "SELECT id, timestamp, event_type FROM telemetry_events "
            "WHERE timestamp >= :start_at AND timestamp < :end_at ORDER BY timestamp, id"
        ), {"start_at": start_at, "end_at": end_at}).mappings().all()
    events = [dict(row) for row in results]
    watermark = max((_utc_datetime(row["timestamp"]) for row in events), default=None)
    return {"events": events, "telemetry_status": "available", "telemetry_watermark": watermark,
            "business_watermark": None, "business_facts": {},
            "business_sources_complete": False, "source_cursors": {}}


@task
def validate_and_deduplicate(batch: dict[str, Any]) -> dict[str, Any]:
    unique: dict[str, tuple[datetime, str]] = {}
    rejected = 0
    for event in batch["events"]:
        timestamp = _utc_datetime(event.get("timestamp"))
        event_id = str(event.get("id", ""))
        event_type = str(event.get("event_type", ""))
        if not event_id or timestamp is None or not event_type:
            rejected += 1
            continue
        signature = (timestamp, event_type)
        if event_id in unique and unique[event_id] != signature:
            rejected += 1
            continue
        unique[event_id] = signature
    return {
        **batch,
        "events": [{"id": key, "timestamp": value[0], "event_type": value[1]} for key, value in unique.items()],
        "rows_read": len(batch["events"]),
        "rows_rejected": rejected,
        "telemetry_watermark": _utc_datetime(batch.get("telemetry_watermark")),
        "business_watermark": _utc_datetime(batch.get("business_watermark")),
    }


# Cache keys include validated facts; ten minutes bounds reuse of potentially stale transformations.
@task(cache_key_fn=task_input_hash, cache_expiration=timedelta(minutes=10), persist_result=True)
def calculate_kpis(validated_batch: dict[str, Any]) -> list[dict[str, Any]]:
    return calculate_business_kpis(**validated_batch.get("business_facts", {}))


def _business_partitions(window_start: date, window_end: date,
                         country_codes: list[str]) -> list[tuple[date, str]]:
    return [(window_start + timedelta(days=offset), country)
            for offset in range((window_end - window_start).days)
            for country in country_codes]


@task(retries=DB_RETRIES, retry_delay_seconds=DB_RETRY_DELAY_SECONDS)
def stage_reporting_partition(rows: list[dict[str, Any]], partitions: list[tuple[date, str]],
                              source_watermark: datetime | None, run_id: str) -> int:
    staged_at = _now()
    watermark = source_watermark or staged_at
    grouped: dict[tuple[date, str], list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault((row["metric_date"], row["country_code"]), []).append(row)
    count = 0
    with get_reporting_engine().begin() as connection:
        for metric_date, country in partitions:
            key = and_(business_kpi_staging.c.run_id == run_id,
                       business_kpi_staging.c.metric_date == metric_date,
                       business_kpi_staging.c.country_code == country)
            connection.execute(delete(business_kpi_staging).where(key))
            marker_key = and_(pipeline_staging_partitions.c.run_id == run_id,
                              pipeline_staging_partitions.c.metric_date == metric_date,
                              pipeline_staging_partitions.c.country_code == country)
            connection.execute(delete(pipeline_staging_partitions).where(marker_key))
            connection.execute(insert(pipeline_staging_partitions).values(
                run_id=run_id, metric_date=metric_date, country_code=country,
                source_watermark=watermark, state="Staged",
            ))
            partition_rows = grouped.get((metric_date, country), [])
            if partition_rows:
                connection.execute(insert(business_kpi_staging), [
                    {**row, "run_id": run_id, "source_watermark": watermark,
                     "refreshed_at": staged_at, "definition_version": DEFINITION_VERSION}
                    for row in partition_rows
                ])
                count += len(partition_rows)
    return count


@task(retries=DB_RETRIES, retry_delay_seconds=DB_RETRY_DELAY_SECONDS)
def publish_reporting_partition(run_id: str) -> int:
    """Replace complete staged partitions atomically, including partitions with zero rows."""
    written = 0
    with get_reporting_engine().begin() as connection:
        markers = connection.execute(select(pipeline_staging_partitions).where(and_(
            pipeline_staging_partitions.c.run_id == run_id,
            pipeline_staging_partitions.c.state == "Staged",
        ))).mappings().all()
        for marker in markers:
            partition = and_(business_kpis_daily.c.metric_date == marker["metric_date"],
                             business_kpis_daily.c.country_code == marker["country_code"])
            connection.execute(delete(business_kpis_daily).where(partition))
            staged_rows = connection.execute(select(business_kpi_staging).where(and_(
                business_kpi_staging.c.run_id == run_id,
                business_kpi_staging.c.metric_date == marker["metric_date"],
                business_kpi_staging.c.country_code == marker["country_code"],
            ))).mappings().all()
            if staged_rows:
                connection.execute(insert(business_kpis_daily), [
                    {column.name: row[column.name] for column in business_kpis_daily.columns}
                    for row in staged_rows
                ])
                written += len(staged_rows)
            connection.execute(update(pipeline_staging_partitions).where(and_(
                pipeline_staging_partitions.c.run_id == run_id,
                pipeline_staging_partitions.c.metric_date == marker["metric_date"],
                pipeline_staging_partitions.c.country_code == marker["country_code"],
            )).values(state="Published"))
    return written


@task(retries=DB_RETRIES, retry_delay_seconds=DB_RETRY_DELAY_SECONDS)
def cleanup_staging(run_id: str) -> None:
    with get_reporting_engine().begin() as connection:
        connection.execute(delete(business_kpi_staging).where(business_kpi_staging.c.run_id == run_id))
        connection.execute(delete(pipeline_staging_partitions).where(pipeline_staging_partitions.c.run_id == run_id))


@task(retries=DB_RETRIES, retry_delay_seconds=DB_RETRY_DELAY_SECONDS)
def enqueue_reprocess_item(source_name: str, country_code: str, metric_date: date, reason: str) -> None:
    key = and_(pipeline_reprocess_queue.c.source_name == source_name,
               pipeline_reprocess_queue.c.country_code == country_code,
               pipeline_reprocess_queue.c.metric_date == metric_date)
    values = {"reason": reason[:240], "status": "Pending", "requested_at": _now(),
              "claimed_by_run_id": None, "completed_at": None}
    with get_reporting_engine().begin() as connection:
        existing = connection.execute(select(pipeline_reprocess_queue).where(key)).first()
        if existing:
            connection.execute(update(pipeline_reprocess_queue).where(key).values(**values))
        else:
            connection.execute(insert(pipeline_reprocess_queue).values(
                source_name=source_name, country_code=country_code, metric_date=metric_date, **values))


@task(retries=DB_RETRIES, retry_delay_seconds=DB_RETRY_DELAY_SECONDS)
def claim_reprocess_items(run_id: str, window_start: date, window_end: date,
                          country_codes: list[str]) -> int:
    with get_reporting_engine().begin() as connection:
        candidates = connection.execute(select(pipeline_reprocess_queue).where(and_(
            pipeline_reprocess_queue.c.status == "Pending",
            pipeline_reprocess_queue.c.metric_date >= window_start,
            pipeline_reprocess_queue.c.metric_date < window_end,
            pipeline_reprocess_queue.c.country_code.in_(country_codes),
        )).with_for_update(skip_locked=True)).mappings().all()
        for item in candidates:
            key = and_(pipeline_reprocess_queue.c.source_name == item["source_name"],
                       pipeline_reprocess_queue.c.country_code == item["country_code"],
                       pipeline_reprocess_queue.c.metric_date == item["metric_date"])
            connection.execute(update(pipeline_reprocess_queue).where(key).values(
                status="Processing", claimed_by_run_id=run_id))
        return len(candidates)


@task(retries=DB_RETRIES, retry_delay_seconds=DB_RETRY_DELAY_SECONDS)
def complete_reprocess_items(run_id: str) -> None:
    with get_reporting_engine().begin() as connection:
        connection.execute(update(pipeline_reprocess_queue).where(and_(
            pipeline_reprocess_queue.c.claimed_by_run_id == run_id,
            pipeline_reprocess_queue.c.status == "Processing",
        )).values(status="Completed", completed_at=_now()))


@task(retries=DB_RETRIES, retry_delay_seconds=DB_RETRY_DELAY_SECONDS)
def release_reprocess_items(run_id: str) -> None:
    with get_reporting_engine().begin() as connection:
        connection.execute(update(pipeline_reprocess_queue).where(and_(
            pipeline_reprocess_queue.c.claimed_by_run_id == run_id,
            pipeline_reprocess_queue.c.status == "Processing",
        )).values(status="Pending", claimed_by_run_id=None))


@task(retries=DB_RETRIES, retry_delay_seconds=DB_RETRY_DELAY_SECONDS)
def commit_source_checkpoint(source_name: str, country_code: str,
                             cursor_timestamp: datetime | None, cursor_id: str | None,
                             committed_through: datetime, run_id: str) -> None:
    key = and_(pipeline_checkpoints.c.source_name == source_name,
               pipeline_checkpoints.c.country_code == country_code)
    values = {"cursor_timestamp": cursor_timestamp, "cursor_id": cursor_id,
              "committed_through": committed_through, "updated_at": _now(),
              "last_successful_run_id": run_id}
    with get_reporting_engine().begin() as connection:
        result = connection.execute(update(pipeline_checkpoints).where(key).values(**values))
        if result.rowcount == 0:
            connection.execute(insert(pipeline_checkpoints).values(
                source_name=source_name, country_code=country_code, **values))


@task(retries=DB_RETRIES, retry_delay_seconds=DB_RETRY_DELAY_SECONDS)
def finalize_pipeline_run(run_id: str, *, state: str, rows_read: int, rows_written: int,
                          rows_rejected: int, source_watermarks: dict[str, Any],
                          error_code: str | None = None,
                          error_message_safe: str | None = None) -> None:
    with get_reporting_engine().begin() as connection:
        connection.execute(update(pipeline_runs).where(pipeline_runs.c.run_id == run_id).values(
            state=state, finished_at=_now(), rows_read=rows_read, rows_written=rows_written,
            rows_rejected=rows_rejected, source_watermarks=source_watermarks,
            error_code=error_code, error_message_safe=error_message_safe,
        ))


def _result(run_id: str, state: str, rows_read: int = 0, rows_written: int = 0,
            rows_rejected: int = 0, error_code: str | None = None) -> dict[str, Any]:
    return {"run_id": run_id, "state": state, "rows_read": rows_read,
            "rows_written": rows_written, "rows_rejected": rows_rejected,
            "error_code": error_code}


@flow(name=FLOW_NAME)
def trackflow_business_performance_flow(window_start: date | None = None,
                                        window_end: date | None = None,
                                        country_codes: list[str] | None = None,
                                        trigger: str = "manual",
                                        requested_by: str | None = None,
                                        run_id: str | None = None) -> dict[str, Any]:
    window_end = window_end or datetime.now(timezone.utc).date()
    window_start = window_start or (window_end - timedelta(days=7))
    country_codes = country_codes or ["US", "ES"]
    _validate_window(window_start, window_end, country_codes)
    run_id = run_id or str(uuid4())
    create_pipeline_run(run_id, window_start, window_end, trigger, requested_by, _now())
    if not acquire_window_locks(run_id, window_start, window_end, country_codes):
        error = "WINDOW_ALREADY_LOCKED"
        finalize_pipeline_run(run_id, state="Failed", rows_read=0, rows_written=0,
                              rows_rejected=0, source_watermarks={}, error_code=error,
                              error_message_safe="La ventana ya está siendo procesada.")
        return _result(run_id, "Failed", error_code=error)

    rows_read = rows_written = rows_rejected = 0
    error_code = error_message_safe = None
    watermarks: dict[str, Any] = {"telemetry_events": "unavailable", "business_sources": "not_configured"}
    source_complete = False
    try:
        extraction_state = extract_source_batch(window_start, window_end, return_state=True)
        if extraction_state.is_completed():
            batch = extraction_state.result()
        else:
            error_code = "OPTIONAL_TELEMETRY_UNAVAILABLE"
            error_message_safe = "La telemetría de contraste no estuvo disponible."
            batch = {"events": [], "telemetry_status": "unavailable", "telemetry_watermark": None,
                     "business_watermark": None, "business_facts": {},
                     "business_sources_complete": False, "source_cursors": {}}
        heartbeat_window_locks(run_id)
        validated = validate_and_deduplicate(batch)
        rows_read = validated["rows_read"]
        rows_rejected = validated["rows_rejected"]
        source_complete = validated["business_sources_complete"] is True
        watermarks = {
            "telemetry_events": validated["telemetry_status"],
            "telemetry_watermark": (validated["telemetry_watermark"].isoformat()
                                     if validated["telemetry_watermark"] else None),
            "business_sources": "complete" if source_complete else "not_configured",
            "business_watermark": (validated["business_watermark"].isoformat()
                                   if validated["business_watermark"] else None),
        }
        metrics = calculate_kpis(validated)
        if source_complete:
            partitions = _business_partitions(window_start, window_end, country_codes)
            claim_reprocess_items(run_id, window_start, window_end, country_codes)
            stage_reporting_partition(metrics, partitions, validated["business_watermark"], run_id)
            heartbeat_window_locks(run_id)
            rows_written = publish_reporting_partition(run_id)
            for source_name, cursors in validated.get("source_cursors", {}).items():
                for country, cursor in cursors.items():
                    commit_source_checkpoint(
                        source_name, country, cursor.get("timestamp"), cursor.get("id"),
                        datetime.combine(window_end, time.min, tzinfo=timezone.utc), run_id)
            complete_reprocess_items(run_id)
            cleanup_staging(run_id)
        state = "Completed"
    except Exception as exc:
        state = "Failed"
        error_code = "PIPELINE_TASK_FAILED"
        error_message_safe = f"Fallo controlado de pipeline: {type(exc).__name__}."
        release_reprocess_items(run_id)
        finalize_pipeline_run(run_id, state=state, rows_read=rows_read, rows_written=rows_written,
                              rows_rejected=rows_rejected, source_watermarks=watermarks,
                              error_code=error_code, error_message_safe=error_message_safe)
        raise
    finally:
        release_window_locks(run_id)
    finalize_pipeline_run(run_id, state=state, rows_read=rows_read, rows_written=rows_written,
                          rows_rejected=rows_rejected, source_watermarks=watermarks,
                          error_code=error_code, error_message_safe=error_message_safe)
    return _result(run_id, state, rows_read, rows_written, rows_rejected, error_code)


def _serialize_run(row: Any) -> dict[str, Any]:
    result = dict(row._mapping)
    for key, value in list(result.items()):
        if isinstance(value, (date, datetime)):
            result[key] = value.isoformat()
    return result


def get_pipeline_status(run_id: str | None = None) -> dict[str, Any] | None:
    statement = select(pipeline_runs)
    if run_id:
        statement = statement.where(pipeline_runs.c.run_id == run_id)
    else:
        statement = statement.order_by(pipeline_runs.c.started_at.desc()).limit(1)
    with get_reporting_engine().connect() as connection:
        row = connection.execute(statement).first()
    return _serialize_run(row) if row else None


def query_business_kpis(start_date: date, end_date: date,
                        country_code: str | None = None,
                        metric_codes: list[str] | None = None) -> list[dict[str, Any]]:
    if start_date >= end_date:
        raise ValueError("start_date must be before end_date; end_date is exclusive")
    statement = select(business_kpis_daily).where(and_(
        business_kpis_daily.c.metric_date >= start_date,
        business_kpis_daily.c.metric_date < end_date,
    ))
    if country_code:
        if country_code not in {"US", "ES"}:
            raise ValueError("country_code must be US or ES")
        statement = statement.where(business_kpis_daily.c.country_code == country_code)
    if metric_codes:
        statement = statement.where(business_kpis_daily.c.metric_code.in_(metric_codes))
    statement = statement.order_by(business_kpis_daily.c.metric_date,
                                   business_kpis_daily.c.country_code,
                                   business_kpis_daily.c.metric_code)
    with get_reporting_engine().connect() as connection:
        rows = connection.execute(statement).all()
    return [{key: value.isoformat() if isinstance(value, (date, datetime)) else value
             for key, value in row._mapping.items()} for row in rows]


def main() -> None:
    print(trackflow_business_performance_flow(trigger="cli"))


if __name__ == "__main__":
    main()
