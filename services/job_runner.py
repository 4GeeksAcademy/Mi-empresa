from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint, Column, Date, DateTime, Index, MetaData, String, Table,
    Text, create_engine, exists, insert, select, text, update,
)
from sqlalchemy.engine import Engine, make_url

metadata = MetaData()
job_runs = Table(
    "job_runs", metadata,
    Column("id", String(36), primary_key=True),
    Column("job_name", String(120), nullable=False),
    Column("target_date", Date, nullable=False),
    Column("status", String(16), nullable=False),
    Column("started_at", DateTime(timezone=True)),
    Column("finished_at", DateTime(timezone=True)),
    Column("error_message", Text),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("status IN ('pending', 'processing', 'completed', 'failed')",
                    name="ck_job_runs_status"),
)
Index("ix_job_runs_job_date", job_runs.c.job_name, job_runs.c.target_date)
Index("uq_job_runs_processing", job_runs.c.job_name, unique=True,
      postgresql_where=text("status = 'processing'"),
      sqlite_where=text("status = 'processing'"))


def create_job_engine(database_url: str) -> Engine:
    url = make_url(database_url)
    url = url.difference_update_query(["pgbouncer"])
    return create_engine(url, pool_pre_ping=True)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def create_run(engine: Engine, job_name: str, target_date: date) -> str:
    run_id = str(uuid4())
    with engine.begin() as connection:
        connection.execute(insert(job_runs).values(
            id=run_id, job_name=job_name, target_date=target_date,
            status="pending", created_at=utc_now(),
        ))
    return run_id


def has_processing_lock(connection, job_name: str) -> bool:
    return bool(connection.scalar(select(exists().where(
        job_runs.c.job_name == job_name, job_runs.c.status == "processing",
    ))))


def has_completed_for_date(connection, job_name: str, target_date: date) -> bool:
    return bool(connection.scalar(select(exists().where(
        job_runs.c.job_name == job_name, job_runs.c.target_date == target_date,
        job_runs.c.status == "completed",
    ))))


def acquire_run(engine: Engine, run_id: str) -> str:
    with engine.begin() as connection:
        if engine.dialect.name == "postgresql":
            connection.execute(text("LOCK TABLE job_runs IN SHARE ROW EXCLUSIVE MODE"))
        elif engine.dialect.name == "sqlite":
            connection.exec_driver_sql("BEGIN IMMEDIATE")
        else:
            raise RuntimeError("job_runner supports PostgreSQL and SQLite only")
        run = connection.execute(select(job_runs).where(job_runs.c.id == run_id)).mappings().one()
        if run["status"] != "pending":
            raise ValueError("Only pending runs can be acquired")
        reason = None
        if has_processing_lock(connection, run["job_name"]):
            reason = "omitted: processing lock"
        elif has_completed_for_date(connection, run["job_name"], run["target_date"]):
            reason = "omitted: already completed for date"
        values = ({"status": "failed", "finished_at": utc_now(), "error_message": reason}
                  if reason else {"status": "processing", "started_at": utc_now()})
        connection.execute(update(job_runs).where(job_runs.c.id == run_id).values(**values))
        return reason or "processing"


def finish_run(engine: Engine, run_id: str, error: str | None = None) -> None:
    with engine.begin() as connection:
        connection.execute(update(job_runs).where(
            job_runs.c.id == run_id, job_runs.c.status.in_(["pending", "processing"]),
        ).values(status="failed" if error else "completed", finished_at=utc_now(),
                 error_message=error))


def get_run(engine: Engine, run_id: str) -> dict:
    with engine.connect() as connection:
        return dict(connection.execute(select(job_runs).where(
            job_runs.c.id == run_id,
        )).mappings().one())