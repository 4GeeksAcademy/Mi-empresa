"""Persist and retrieve owner-scoped execution traces separately from checkpoints."""

import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import UUID


def agent_data_directory() -> Path:
    configured = os.environ.get("TRACKFLOW_AGENT_DATA_DIR")
    return (
        Path(configured)
        if configured
        else Path(__file__).resolve().parents[2] / ".agent-data"
    )


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentTraceStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self._lock = RLock()

    def _connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            connection = self._connect()
            try:
                with connection:
                    yield connection
            finally:
                connection.close()

    def setup(self) -> None:
        with self._connection() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS agent_traces (
                    trace_id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    question TEXT NOT NULL,
                    nodes TEXT NOT NULL DEFAULT '[]',
                    answer TEXT,
                    error_code TEXT,
                    created_at TEXT NOT NULL,
                    completed_at TEXT
                )
            """)
            connection.execute("""
                CREATE INDEX IF NOT EXISTS idx_agent_traces_owner_created
                ON agent_traces(owner_id, created_at)
            """)

    def create(self, trace_id: str, owner_id: str, question: str) -> None:
        UUID(trace_id)
        with self._connection() as connection:
            connection.execute(
                """INSERT INTO agent_traces
                   (trace_id, owner_id, status, question, created_at)
                   VALUES (?, ?, 'running', ?, ?)""",
                (trace_id, owner_id, question, _timestamp()),
            )

    def start_node(
        self, trace_id: str, node: str, input_state: dict[str, Any]
    ) -> None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT nodes FROM agent_traces WHERE trace_id = ?",
                (trace_id,),
            ).fetchone()
            if row is None:
                raise LookupError("Agent trace does not exist.")
            nodes = json.loads(row["nodes"])
            nodes.append({
                "order": len(nodes) + 1,
                "node": node,
                "status": "running",
                "input": input_state,
                "output": None,
            })
            connection.execute(
                "UPDATE agent_traces SET nodes = ? WHERE trace_id = ?",
                (json.dumps(nodes, ensure_ascii=False), trace_id),
            )

    def complete_node(
        self, trace_id: str, node: str, output: dict[str, Any]
    ) -> None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT nodes FROM agent_traces WHERE trace_id = ?",
                (trace_id,),
            ).fetchone()
            if row is None:
                raise LookupError("Agent trace does not exist.")
            nodes = json.loads(row["nodes"])
            if not nodes or nodes[-1]["node"] != node or nodes[-1]["status"] != "running":
                raise LookupError("Agent node start event is missing.")
            nodes[-1]["status"] = "completed"
            nodes[-1]["output"] = output
            connection.execute(
                "UPDATE agent_traces SET nodes = ? WHERE trace_id = ?",
                (json.dumps(nodes, ensure_ascii=False), trace_id),
            )

    def fail_node(self, trace_id: str, node: str) -> None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT nodes FROM agent_traces WHERE trace_id = ?",
                (trace_id,),
            ).fetchone()
            if row is None:
                raise LookupError("Agent trace does not exist.")
            nodes = json.loads(row["nodes"])
            if not nodes or nodes[-1]["node"] != node or nodes[-1]["status"] != "running":
                raise LookupError("Agent node start event is missing.")
            nodes[-1]["status"] = "failed"
            nodes[-1]["error_code"] = "node_error"
            connection.execute(
                "UPDATE agent_traces SET nodes = ? WHERE trace_id = ?",
                (json.dumps(nodes, ensure_ascii=False), trace_id),
            )

    def finish(
        self,
        trace_id: str,
        *,
        status: str,
        answer: str | None = None,
        error_code: str | None = None,
    ) -> None:
        if status not in {"completed", "rejected", "failed"}:
            raise ValueError("Invalid terminal trace status.")
        with self._connection() as connection:
            cursor = connection.execute(
                """UPDATE agent_traces
                   SET status = ?, answer = ?, error_code = ?, completed_at = ?
                   WHERE trace_id = ? AND status = 'running'""",
                (status, answer, error_code, _timestamp(), trace_id),
            )
            if cursor.rowcount != 1:
                raise LookupError("Agent trace is not running.")

    def get_for_owner(self, trace_id: str, owner_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM agent_traces WHERE trace_id = ? AND owner_id = ?",
                (trace_id, owner_id),
            ).fetchone()
        if row is None:
            return None
        return {
            "trace_id": row["trace_id"],
            "status": row["status"],
            "question": row["question"],
            "nodes": json.loads(row["nodes"]),
            "answer": row["answer"],
            "error_code": row["error_code"],
            "created_at": row["created_at"],
            "completed_at": row["completed_at"],
        }
