import csv
import json
import logging
import multiprocessing
import os
import selectors
import signal
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import (
    JSON, Column, DateTime, Float, MetaData, String, Table, Text,
    create_engine, insert, select, text,
)
from sqlalchemy.engine import make_url

from scripts import nightly_export as nightly
from services import job_runner as jobs

TARGET = date(2026, 10, 18)
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(params=["sqlite", "postgresql"])
def engine(request, tmp_path):
    admin = None
    schema = None
    if request.param == "postgresql":
        database_url = os.getenv("TEST_JOB_DATABASE_URL")
        if not database_url:
            pytest.skip("Set TEST_JOB_DATABASE_URL to a disposable local PostgreSQL database")
        url = make_url(database_url)
        if url.host not in {"localhost", "127.0.0.1"} or "dev53" not in url.database:
            pytest.fail("PostgreSQL tests require a local database with dev53 in its name")
        admin = create_engine(url)
        schema = "test_" + uuid4().hex
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        url = url.update_query_dict({"options": f"-csearch_path={schema}"})
        database = create_engine(url)
        migration = ROOT / "services/api/migrations/20261019_job_runs.sql"
        raw = database.raw_connection()
        try:
            with raw.cursor() as cursor:
                cursor.execute(migration.read_text())
            raw.commit()
        finally:
            raw.close()
    else:
        database = create_engine(f"sqlite:///{tmp_path / 'test.sqlite3'}")
        jobs.metadata.create_all(database)
    event_metadata = MetaData()
    events = Table(
        "telemetry_events", event_metadata,
        Column("id", String, primary_key=True),
        Column("timestamp", DateTime, nullable=False),
        Column("service", String), Column("event_type", String),
        Column("level", String), Column("value", Float),
        Column("message", Text), Column("tags", JSON),
    )
    event_metadata.create_all(database)
    start = datetime(2026, 10, 18)
    with database.begin() as connection:
        connection.execute(insert(events), [
            {"id": str(uuid4()), "timestamp": stamp, "service": "api",
             "event_type": "api_latency_recorded", "level": "info", "value": 1.5,
             "message": "quoted, message\nsecond line", "tags": {"country": "ES"}}
            for stamp in [start - timedelta(microseconds=1), start,
                          start + timedelta(days=1, microseconds=-1), start + timedelta(days=1)]
        ])
    try:
        yield database
    finally:
        database.dispose()
        if admin is not None:
            with admin.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            admin.dispose()


def runs(engine):
    with engine.connect() as connection:
        return connection.execute(select(jobs.job_runs).order_by(jobs.job_runs.c.created_at)).mappings().all()


@pytest.mark.parametrize("value", ["", "2026-1-01", "2026-02-30", "20261018", "2026-10-18T00:00:00"])
def test_invalid_target_date(value):
    with pytest.raises(ValueError):
        nightly.resolve_target_date(value)


def test_target_date_utc():
    assert nightly.resolve_target_date("2026-10-18") == TARGET
    now = datetime(2026, 10, 19, 1, tzinfo=timezone(timedelta(hours=2)))
    assert nightly.resolve_target_date(None, now) == date(2026, 10, 17)


def test_state_machine_and_helpers(engine):
    run_id = jobs.create_run(engine, nightly.JOB_NAME, TARGET)
    assert jobs.get_run(engine, run_id)["status"] == "pending"
    assert jobs.acquire_run(engine, run_id) == "processing"
    running = jobs.get_run(engine, run_id)
    assert running["started_at"] is not None and running["finished_at"] is None
    with engine.connect() as connection:
        assert jobs.has_processing_lock(connection, nightly.JOB_NAME)
        assert not jobs.has_completed_for_date(connection, nightly.JOB_NAME, TARGET)
    jobs.finish_run(engine, run_id)
    completed = jobs.get_run(engine, run_id)
    assert completed["status"] == "completed" and completed["finished_at"] is not None


def test_success_duplicate_and_different_dates(engine, tmp_path, monkeypatch, caplog):
    invocations = []
    monkeypatch.setattr(nightly, "launch_pipeline", invocations.append)
    caplog.set_level(logging.INFO, logger=nightly.JOB_NAME)
    assert nightly.run_job(engine, TARGET, tmp_path) == 0
    destination = tmp_path / f"telemetry_{TARGET}.csv"
    original = destination.read_bytes()
    with destination.open(newline="") as handle:
        exported = list(csv.DictReader(handle))
    assert len(exported) == 2
    assert json.loads(exported[0]["tags"]) == {"country": "ES"}
    assert exported[0]["message"] == "quoted, message\nsecond line"
    assert nightly.run_job(engine, TARGET, tmp_path) == 0
    assert invocations == [TARGET]
    assert destination.read_bytes() == original
    assert nightly.run_job(engine, TARGET + timedelta(days=1), tmp_path) == 0
    assert len(invocations) == 2
    assert [row["status"] for row in runs(engine)] == ["completed", "failed", "completed"]
    assert runs(engine)[1]["started_at"] is None
    assert "already completed" in caplog.text
    assert all("job_name=nightly_export target_date=" in record.message and "status=" in record.message
               for record in caplog.records)


@pytest.mark.parametrize("failure", ["export", "pipeline", "interrupt"])
def test_failure_and_retry(engine, tmp_path, monkeypatch, failure):
    real_export = nightly.export_csv
    def fail(*arguments):
        if failure == "interrupt":
            raise InterruptedError("test signal")
        if failure == "pipeline":
            raise subprocess.CalledProcessError(7, ["test-pipeline"])
        raise OSError("test export error")
    monkeypatch.setattr(nightly, "launch_pipeline", fail if failure != "export" else lambda target: None)
    if failure == "export":
        monkeypatch.setattr(nightly, "export_csv", fail)
    assert nightly.run_job(engine, TARGET, tmp_path) == 1
    failed = runs(engine)[0]
    assert failed["status"] == "failed" and failed["finished_at"] is not None
    assert failed["error_message"]
    assert not any(row["status"] == "processing" for row in runs(engine))
    monkeypatch.setattr(nightly, "export_csv", real_export)
    monkeypatch.setattr(nightly, "launch_pipeline", lambda target: None)
    assert nightly.run_job(engine, TARGET, tmp_path) == 0
    assert [row["status"] for row in runs(engine)] == ["failed", "completed"]


def test_existing_csv_still_runs_pipeline(engine, tmp_path, monkeypatch):
    destination = tmp_path / f"telemetry_{TARGET}.csv"
    destination.write_text("existing backup\n")
    calls = []
    monkeypatch.setattr(nightly, "launch_pipeline", calls.append)
    assert nightly.run_job(engine, TARGET, tmp_path) == 0
    assert destination.read_text() == "existing backup\n"
    assert calls == [TARGET]


def test_partial_export_is_removed(engine, tmp_path, monkeypatch):
    def fail(value):
        raise ValueError("serialization error")
    monkeypatch.setattr(nightly, "serialize_cell", fail)
    with pytest.raises(ValueError, match="serialization"):
        nightly.export_csv(engine, TARGET, tmp_path)
    assert list(tmp_path.glob("*.csv")) == []
    assert list(tmp_path.glob(".telemetry_*")) == []


def competing_worker(database_url, output_dir, start, release, messages):
    from scripts import nightly_export as worker
    database = jobs.create_job_engine(database_url)
    def pipeline(target):
        messages.put("pipeline")
        if not release.wait(20):
            raise TimeoutError("test worker release")
    worker.launch_pipeline = pipeline
    start.wait(20)
    code = worker.run_job(database, TARGET, Path(output_dir))
    messages.put(("exit", code))
    database.dispose()


def test_two_independent_processes_only_one_works(engine, tmp_path):
    context = multiprocessing.get_context("spawn")
    start, release = context.Event(), context.Event()
    messages = context.Queue()
    processes = [context.Process(target=competing_worker, args=(
        engine.url.render_as_string(hide_password=False), str(tmp_path), start, release, messages,
    )) for number in range(2)]
    try:
        for process in processes:
            process.start()
        start.set()
        observed = [messages.get(timeout=25), messages.get(timeout=25)]
        assert sorted(observed, key=str) == sorted(["pipeline", ("exit", 0)], key=str)
        assert [row["status"] for row in runs(engine)].count("processing") == 1
        release.set()
        assert messages.get(timeout=25) == ("exit", 0)
        for process in processes:
            process.join(timeout=10)
            assert process.exitcode == 0
        records = runs(engine)
        assert sorted(row["status"] for row in records) == ["completed", "failed"]
        assert any(row["error_message"] == "omitted: processing lock" for row in records)
        assert len(list(tmp_path.glob("*.csv"))) == 1
    finally:
        release.set()
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)


def test_lock_applies_across_dates(engine):
    first = jobs.create_run(engine, nightly.JOB_NAME, TARGET)
    assert jobs.acquire_run(engine, first) == "processing"
    second = jobs.create_run(engine, nightly.JOB_NAME, TARGET + timedelta(days=1))
    assert jobs.acquire_run(engine, second) == "omitted: processing lock"
    jobs.finish_run(engine, first, "test cleanup")


def test_subprocess_failure_is_checked(monkeypatch):
    monkeypatch.setattr(nightly, "pipeline_command", lambda target: [sys.executable, "-c", "raise SystemExit(7)"])
    with pytest.raises(subprocess.CalledProcessError) as error:
        nightly.launch_pipeline(TARGET)
    assert error.value.returncode == 7


def test_cli_invalid_date_outside_repository(tmp_path):
    result = subprocess.run([sys.executable, str(ROOT / "scripts/nightly_export.py")],
                            cwd=tmp_path, env={**os.environ, "TARGET_DATE": "bad"},
                            text=True, capture_output=True, timeout=20)
    assert result.returncode == 1
    assert "TARGET_DATE" in result.stderr and "status=failed" in result.stderr
    assert "Traceback" not in result.stderr


def test_sigterm_stops_child_and_marks_failed(engine, tmp_path):
    target = date(2091, 1, 4)
    destination = ROOT / f"data/raw/telemetry_{target}.csv"
    assert not destination.exists()
    child_code = "import os,signal; print('child-ready='+str(os.getpid()),flush=True); signal.pause()"
    worker_code = (
        "import sys; from scripts import nightly_export as n; "
        f"n.pipeline_command=lambda target: [sys.executable, '-c', {child_code!r}]; "
        "raise SystemExit(n.main())"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", worker_code], cwd=ROOT, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        env={**os.environ, "DATABASE_URL": engine.url.render_as_string(hide_password=False),
             "TARGET_DATE": str(target)},
    )
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    child_pid = None
    try:
        while child_pid is None:
            assert selector.select(timeout=20), "worker did not launch child"
            line = process.stdout.readline()
            assert line, "worker exited before child readiness"
            if "child-ready=" in line:
                child_pid = int(line.rsplit("=", 1)[1])
        process.send_signal(signal.SIGTERM)
        output, _ = process.communicate(timeout=20)
        assert process.returncode == 1
        assert "InterruptedError" in output
        assert runs(engine)[0]["status"] == "failed"
        assert runs(engine)[0]["finished_at"] is not None
        with pytest.raises(ProcessLookupError):
            os.kill(child_pid, 0)
    finally:
        selector.close()
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        if child_pid is not None:
            try:
                os.kill(child_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.stdout.close()
        destination.unlink(missing_ok=True)


def test_real_pipeline_cli_and_separate_tables(engine, tmp_path):
    if engine.dialect.name != "postgresql":
        pytest.skip("Real flow integration is verified on PostgreSQL")
    target = date(2091, 1, 3)
    destination = ROOT / f"data/raw/telemetry_{target}.csv"
    assert not destination.exists()
    environment = {**os.environ, "DATABASE_URL": engine.url.render_as_string(hide_password=False),
                   "TARGET_DATE": str(target), "PREFECT_HOME": str(tmp_path / "prefect"),
                   "PREFECT_SERVER_ANALYTICS_ENABLED": "false", "DO_NOT_TRACK": "1"}
    environment.pop("PREFECT_API_URL", None)
    try:
        result = subprocess.run([sys.executable, str(ROOT / "scripts/nightly_export.py")],
                                cwd=tmp_path, env=environment, text=True, capture_output=True, timeout=150)
        assert result.returncode == 0, result.stderr[-6000:]
        assert destination.exists()
        assert runs(engine)[0]["status"] == "completed"
        with engine.connect() as connection:
            pipeline = connection.execute(text(
                "SELECT state, window_start, window_end FROM reporting.pipeline_runs "
                "WHERE window_start = '2091-01-03' ORDER BY started_at DESC LIMIT 1"
            )).mappings().one()
        assert pipeline["state"] == "Completed"
        assert pipeline["window_start"] == target
        assert pipeline["window_end"] == target + timedelta(days=1)
        assert "job_name=nightly_export" in result.stderr
        subprocess.run(
            [sys.executable, "-c",
             "import sys; import scripts.nightly_export; assert 'fastapi' not in sys.modules"],
            cwd=ROOT, check=True, timeout=20,
        )
    finally:
        destination.unlink(missing_ok=True)


def test_apscheduler_calendar_is_explicitly_utc():
    from threading import Event
    from scripts import nightly_scheduler as scheduling

    scheduler = scheduling.create_scheduler(Event())
    job = scheduler.get_job("nightly_export")
    next_run = job.trigger.get_next_fire_time(
        None, datetime(2026, 10, 19, 2, 31, tzinfo=timezone.utc),
    )
    assert next_run == datetime(2026, 10, 20, 2, 30, tzinfo=timezone.utc)
    assert str(job.trigger.timezone) == "UTC"
    assert job.max_instances == 2
    assert job.coalesce is True
    assert job.misfire_grace_time == 3600


@pytest.mark.parametrize("exit_code", [0, 7])
def test_scheduler_launches_independent_process(monkeypatch, exit_code):
    from threading import Event
    from scripts import nightly_scheduler as scheduling

    actual_popen = subprocess.Popen
    calls = []
    def launch(command, **kwargs):
        calls.append((command, kwargs))
        return actual_popen([sys.executable, "-c", f"raise SystemExit({exit_code})"], **kwargs)
    monkeypatch.setattr(scheduling.subprocess, "Popen", launch)
    assert scheduling.run_export(Event()) == exit_code
    assert calls[0][0] == [sys.executable, str(ROOT / "scripts/nightly_export.py")]
    assert calls[0][1]["cwd"] == ROOT
    assert "shell" not in calls[0][1]


def test_real_apscheduler_trigger_executes_subprocess(monkeypatch):
    from threading import Event, Thread
    from apscheduler.events import EVENT_JOB_EXECUTED
    from apscheduler.triggers.date import DateTrigger
    from scripts import nightly_scheduler as scheduling

    actual_popen = subprocess.Popen
    calls = []
    def launch(command, **kwargs):
        calls.append(command)
        return actual_popen([sys.executable, "-c", "print('real scheduler trigger')"], **kwargs)
    monkeypatch.setattr(scheduling.subprocess, "Popen", launch)
    scheduler = scheduling.create_scheduler(Event())
    scheduler.reschedule_job("nightly_export", trigger=DateTrigger(run_date=datetime.now(timezone.utc)))
    done = Event()
    results = []
    def finished(event):
        results.append(event.retval)
        done.set()
    scheduler.add_listener(finished, EVENT_JOB_EXECUTED)
    thread = Thread(target=scheduler.start, daemon=True)
    thread.start()
    try:
        assert done.wait(15), "APScheduler did not execute the subprocess"
        assert results == [0]
        assert len(calls) == 1
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=True)
        thread.join(timeout=5)
        assert not thread.is_alive()


def test_scheduler_shutdown_terminates_active_export(monkeypatch):
    from threading import Event
    from scripts import nightly_scheduler as scheduling

    actual_popen = subprocess.Popen
    stopping = Event()
    children = []
    def launch(command, **kwargs):
        child = actual_popen([sys.executable, "-c", "import signal; signal.pause()"], **kwargs)
        children.append(child)
        stopping.set()
        return child
    monkeypatch.setattr(scheduling.subprocess, "Popen", launch)
    assert scheduling.run_export(stopping) != 0
    assert children[0].poll() is not None


def test_scheduler_cli_check_and_sigterm(tmp_path):
    command = [sys.executable, str(ROOT / "scripts/nightly_scheduler.py")]
    checked = subprocess.run(command + ["--check"], cwd=tmp_path,
                             text=True, capture_output=True, timeout=15)
    assert checked.returncode == 0
    assert "cron=30 2 * * * timezone=UTC" in checked.stderr
    subprocess.run(
        [sys.executable, "-c", "import sys; import scripts.nightly_scheduler; assert 'fastapi' not in sys.modules"],
        cwd=ROOT, check=True, timeout=15,
    )
    process = subprocess.Popen(
        command, cwd=tmp_path, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        env={**os.environ, "DATABASE_URL": "postgresql+psycopg2://unused@127.0.0.1:1/dev53"},
    )
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    output = b""
    try:
        while b"Scheduler started" not in output:
            assert selector.select(timeout=15), "scheduler did not start"
            chunk = os.read(process.stdout.fileno(), 4096)
            assert chunk, "scheduler exited before startup"
            output += chunk
        process.send_signal(signal.SIGTERM)
        remaining, _ = process.communicate(timeout=15)
        assert process.returncode == 0
        assert b"Scheduler has been shut down" in remaining
        assert b"Launching independent export" not in output + remaining
    finally:
        selector.close()
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        process.stdout.close()