from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from datetime import date, datetime, time as day_time, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import MetaData, Table, select

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from services import job_runner

JOB_NAME = "nightly_export"
logger = logging.getLogger(JOB_NAME)


def resolve_target_date(value: str | None, now: datetime | None = None) -> date:
    if value is not None:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("TARGET_DATE must use YYYY-MM-DD")
        return date.fromisoformat(value)
    return (now or datetime.now(timezone.utc)).astimezone(timezone.utc).date() - timedelta(days=1)


def log_event(level: int, target_date: date | None, status: str, message: str) -> None:
    for line in message.splitlines() or [""]:
        logger.log(level, "job_name=%s target_date=%s status=%s %s",
                   JOB_NAME, target_date, status, line)


def serialize_cell(value):
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def export_csv(engine, target_date: date, output_dir: Path) -> Path:
    destination = output_dir / f"telemetry_{target_date.isoformat()}.csv"
    if destination.exists():
        return destination
    output_dir.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with engine.connect() as connection:
            events = Table("telemetry_events", MetaData(), autoload_with=connection)
            start = datetime.combine(target_date, day_time.min, tzinfo=timezone.utc)
            end = start + timedelta(days=1)
            if not getattr(events.c.timestamp.type, "timezone", False):
                start, end = start.replace(tzinfo=None), end.replace(tzinfo=None)
            query = select(events).where(events.c.timestamp >= start, events.c.timestamp < end)
            query = query.order_by(events.c.timestamp, events.c.id)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="",
                                             dir=output_dir, prefix=".telemetry_",
                                             suffix=".tmp", delete=False) as handle:
                temporary = Path(handle.name)
                writer = csv.writer(handle)
                writer.writerow(events.c.keys())
                for row in connection.execution_options(stream_results=True).execute(query):
                    writer.writerow([serialize_cell(value) for value in row])
                handle.flush()
                os.fsync(handle.fileno())
        try:
            os.link(temporary, destination)
        except FileExistsError:
            pass
        return destination
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def pipeline_command(target_date: date) -> list[str]:
    return [sys.executable, str(Path(__file__).resolve()), "--pipeline", target_date.isoformat()]


def launch_pipeline(target_date: date) -> None:
    command = pipeline_command(target_date)
    process = subprocess.Popen(command, cwd=REPOSITORY_ROOT, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, start_new_session=True)
    try:
        for line in process.stdout:
            log_event(logging.INFO, target_date, "processing", f"pipeline: {line.rstrip()}")
        returncode = process.wait()
        if returncode:
            raise subprocess.CalledProcessError(returncode, command)
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        process.stdout.close()


def run_job(engine, target_date: date, output_dir: Path | None = None) -> int:
    run_id = job_runner.create_run(engine, JOB_NAME, target_date)
    log_event(logging.INFO, target_date, "pending", f"created run_id={run_id}")
    try:
        outcome = job_runner.acquire_run(engine, run_id)
        if outcome != "processing":
            log_event(logging.INFO, target_date, "failed", outcome)
            return 0
        log_event(logging.INFO, target_date, "processing", f"started run_id={run_id}")
        export_csv(engine, target_date, output_dir or REPOSITORY_ROOT / "data/raw")
        launch_pipeline(target_date)
        job_runner.finish_run(engine, run_id)
        log_event(logging.INFO, target_date, "completed", f"finished run_id={run_id}")
        return 0
    except BaseException as error:
        try:
            job_runner.finish_run(engine, run_id, f"{type(error).__name__}: {error}")
        except Exception:
            log_event(logging.ERROR, target_date, "unknown", "cannot persist failed; operator action required")
        log_event(logging.ERROR, target_date, "failed", f"{type(error).__name__}: {error}")
        return 1


def interrupt(signum, frame) -> None:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    raise InterruptedError(f"Received signal {signum}")


def main() -> int:
    logging.Formatter.converter = time.gmtime
    logging.basicConfig(level=logging.INFO, format="%(asctime)sZ %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Independent nightly telemetry export")
    parser.add_argument("--pipeline", type=date.fromisoformat, help=argparse.SUPPRESS)
    arguments = parser.parse_args()
    target_date = None
    engine = None
    previous_handlers = {}
    try:
        load_dotenv(REPOSITORY_ROOT / ".env")
        if arguments.pipeline:
            from data.pipelines.pipeline import trackflow_business_performance_flow

            result = trackflow_business_performance_flow(
                window_start=arguments.pipeline,
                window_end=arguments.pipeline + timedelta(days=1), trigger="cli",
            )
            return 0 if result["state"] == "Completed" else 1
        target_date = resolve_target_date(os.getenv("TARGET_DATE"))
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL is required; apply the job_runs migration first")
        engine = job_runner.create_job_engine(database_url)
        for signum in (signal.SIGTERM, signal.SIGINT):
            previous_handlers[signum] = signal.signal(signum, interrupt)
        return run_job(engine, target_date)
    except Exception as error:
        log_event(logging.ERROR, target_date, "failed", f"{type(error).__name__}: {error}")
        return 1
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    sys.exit(main())