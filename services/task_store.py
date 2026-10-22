from __future__ import annotations

import json
import os
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO
from uuid import UUID


def storage_dir() -> Path:
    directory = Path(os.environ.get("TASK_DATA_DIR", "/tmp/trackflow-tasks"))
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def task_path(task_id: str, suffix: str) -> Path:
    return storage_dir() / f"{UUID(task_id)}.{suffix}"


@contextmanager
def connection():
    database = sqlite3.connect(storage_dir() / "tasks.sqlite3", timeout=10)
    database.row_factory = sqlite3.Row
    try:
        database.executescript("""
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY, owner TEXT NOT NULL,
                filename TEXT NOT NULL, result TEXT, completed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS dead_letters (
                task_id TEXT PRIMARY KEY REFERENCES tasks(task_id),
                attempt INTEGER NOT NULL, error TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );
        """)
        with database:
            yield database
    finally:
        database.close()


def create_upload(task_id: str, owner: str, filename: str, source: BinaryIO) -> None:
    path = task_path(task_id, "csv")
    try:
        with path.open("xb") as destination:
            shutil.copyfileobj(source, destination)
        if path.stat().st_size == 0:
            raise ValueError("El fichero CSV esta vacio.")
        with connection() as database:
            database.execute(
                "INSERT INTO tasks(task_id, owner, filename) VALUES (?, ?, ?)",
                (task_id, owner, filename),
            )
    except Exception:
        path.unlink(missing_ok=True)
        raise


def discard_upload(task_id: str) -> None:
    with connection() as database:
        database.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
    task_path(task_id, "csv").unlink(missing_ok=True)


def get_job(task_id: str) -> dict | None:
    with connection() as database:
        row = database.execute(
            "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
    return dict(row) if row else None


def complete_job(task_id: str, result: dict, export: bytes) -> None:
    temporary = task_path(task_id, "export.tmp")
    temporary.write_bytes(export)
    temporary.replace(task_path(task_id, "export.csv"))
    with connection() as database:
        database.execute(
            "UPDATE tasks SET result = ?, completed_at = ? WHERE task_id = ?",
            (json.dumps(result), datetime.now(timezone.utc).isoformat(), task_id),
        )


def latest_export() -> bytes | None:
    with connection() as database:
        row = database.execute(
            "SELECT task_id FROM tasks WHERE result IS NOT NULL "
            "ORDER BY completed_at DESC LIMIT 1"
        ).fetchone()
    return task_path(row["task_id"], "export.csv").read_bytes() if row else None


def record_failure(task_id: str, attempt: int, error: str) -> None:
    with connection() as database:
        database.execute(
            "INSERT INTO dead_letters(task_id, attempt, error, timestamp) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(task_id) DO NOTHING",
            (task_id, attempt, error, datetime.now(timezone.utc).isoformat()),
        )


def get_failure(task_id: str) -> dict | None:
    with connection() as database:
        row = database.execute(
            "SELECT * FROM dead_letters WHERE task_id = ?", (task_id,)
        ).fetchone()
    return dict(row) if row else None