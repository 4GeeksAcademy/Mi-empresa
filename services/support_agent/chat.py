"""In-memory chat sessions, event pub/sub, and cancellable agent producers."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from collections import defaultdict
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from langgraph.graph.state import CompiledStateGraph

from services.knowledge import pipeline
from services.support_agent.execution import AgentExecutionError, execute_agent
from services.support_agent.graph import AgentInput
from services.support_agent.memory import AgentMemoryStore
from services.support_agent.traces import AgentTraceStore


@dataclass
class ChatSession:
    session_id: str
    agent_id: str
    user_id: str
    client_id: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = "active"
    messages: list[dict[str, Any]] = field(default_factory=list)
    generation_id: str | None = None
    cancelled: threading.Event | None = None
    abort_provider: Callable[[], None] | None = None
    future: Future | None = None


@dataclass(frozen=True)
class _Subscriber:
    queue: asyncio.Queue[dict[str, Any]]
    loop: asyncio.AbstractEventLoop | None


class ChatHub:
    """Single-process session store and per-session asyncio pub/sub queues."""

    def __init__(self, database_path: Path | None = None) -> None:
        self.sessions: dict[str, ChatSession] = {}
        self._subscribers: dict[str, set[_Subscriber]] = defaultdict(set)
        self._turn_locks: dict[str, asyncio.Lock] = {}
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="cx-chat")
        self._database_path = database_path
        if database_path is not None:
            database_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(database_path) as connection:
                connection.execute("""CREATE TABLE IF NOT EXISTS chat_sessions (
                    session_id TEXT PRIMARY KEY, agent_id TEXT NOT NULL,
                    user_id TEXT NOT NULL, client_id TEXT NOT NULL,
                    status TEXT NOT NULL, messages TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )""")
                columns = {row[1] for row in connection.execute("PRAGMA table_info(chat_sessions)")}
                if "created_at" not in columns:
                    connection.execute(
                        "ALTER TABLE chat_sessions ADD COLUMN created_at TEXT NOT NULL DEFAULT ''"
                    )
                    connection.execute(
                        "UPDATE chat_sessions SET created_at = CURRENT_TIMESTAMP WHERE created_at = ''"
                    )

    def _persist(self, session: ChatSession) -> None:
        if self._database_path is None:
            return
        with sqlite3.connect(self._database_path, timeout=30) as connection:
            connection.execute("""INSERT INTO chat_sessions
                (session_id, agent_id, user_id, client_id, status, messages, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                  status=excluded.status, messages=excluded.messages""",
                (session.session_id, session.agent_id, session.user_id,
                 session.client_id, session.status,
                 json.dumps(session.messages, ensure_ascii=False), session.created_at))

    def get_or_create(self, session_id: str, user_id: str, client_id: str) -> ChatSession:
        with self._lock:
            session = self.sessions.get(session_id)
            if session is None and self._database_path is not None:
                with sqlite3.connect(self._database_path, timeout=30) as connection:
                    connection.row_factory = sqlite3.Row
                    row = connection.execute(
                        "SELECT * FROM chat_sessions WHERE session_id = ?", (session_id,),
                    ).fetchone()
                if row is not None:
                    session = ChatSession(
                        row["session_id"], row["agent_id"], row["user_id"],
                        row["client_id"], row["created_at"], row["status"],
                        json.loads(row["messages"]),
                    )
                    for message in session.messages:
                        if message.get("role") == "assistant" and message.get("status") == "streaming":
                            message["status"] = "interrupted"
                            session.status = "interrupted"
                    self.sessions[session_id] = session
                    self._persist(session)
            if session is None:
                session = ChatSession(session_id, "first_line_cx", user_id, client_id)
                self.sessions[session_id] = session
                self._persist(session)
            elif session.user_id != user_id or session.client_id != client_id:
                raise PermissionError("Chat session belongs to another user.")
            return session

    def subscribe(self, session_id: str) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        with self._lock:
            self._subscribers[session_id].add(_Subscriber(queue, loop))
        return queue

    def unsubscribe(self, session_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        with self._lock:
            subscribers = self._subscribers[session_id]
            subscribers.difference_update(
                {item for item in subscribers if item.queue is queue}
            )

    def turn_lock(self, session_id: str) -> asyncio.Lock:
        """Serialize turns for a session even when several sockets are subscribed."""
        with self._lock:
            return self._turn_locks.setdefault(session_id, asyncio.Lock())

    def publish(self, session_id: str, event: dict[str, Any]) -> None:
        with self._lock:
            subscribers = tuple(self._subscribers[session_id])
        for subscriber in subscribers:
            if subscriber.loop is None:
                subscriber.queue.put_nowait(event)
                continue
            try:
                subscriber.loop.call_soon_threadsafe(subscriber.queue.put_nowait, event)
            except RuntimeError:
                self.unsubscribe(session_id, subscriber.queue)

    def register(self, session: ChatSession) -> None:
        """Register an externally constructed session (also useful for tests)."""
        with self._lock:
            self.sessions[session.session_id] = session
            self._persist(session)

    def snapshot(self, session: ChatSession) -> dict[str, Any]:
        with self._lock:
            return {
                "event": "session_snapshot",
                "data": {
                    "session_id": session.session_id,
                    "messages": [dict(message) for message in session.messages],
                    "agent_id": session.agent_id,
                    "user_id": session.user_id,
                    "client_id": session.client_id,
                    "status": session.status,
                    "created_at": session.created_at,
                },
            }

    def add_user_message(self, session: ChatSession, text: str) -> None:
        with self._lock:
            session.messages.append({
                "message_id": f"msg_{uuid4().hex}", "role": "user", "text": text,
                "status": "completed",
            })
            self._persist(session)
        self.publish(session.session_id, {
            "event": "user_message",
            "data": {"session_id": session.session_id, "text": text},
        })

    def start_turn(
        self,
        session: ChatSession,
        text: str,
        graph: CompiledStateGraph[Any, Any, Any, Any],
        traces: AgentTraceStore,
        memory: AgentMemoryStore,
    ) -> None:
        with self._lock:
            generation_id = f"gen_{uuid4().hex}"
            if self.sessions.get(session.session_id) is not session:
                self.sessions[session.session_id] = session
            message_id = f"msg_{uuid4().hex}"
            cancel = threading.Event()
            session.status = "active"
            session.generation_id = generation_id
            session.cancelled = cancel
            session.abort_provider = None
            session.messages.append({
                "message_id": message_id, "role": "assistant", "text": "",
                "status": "streaming", "generation_id": generation_id,
            })
            self._persist(session)

        def emit_token(token: str) -> None:
            with self._lock:
                if cancel.is_set() or session.generation_id != generation_id:
                    return
                message = next(
                    item for item in session.messages if item["message_id"] == message_id
                )
                message["text"] += token
                sequence = message.get("sequence", 0) + 1
                message["sequence"] = sequence
                self._persist(session)
            self.publish(session.session_id, {
                "event": "token_chunk",
                "data": {"session_id": session.session_id, "token": token,
                         "sequence": sequence, "generation_id": generation_id,
                         "message_id": message_id},
            })

        def register_abort(callback: Callable[[], None]) -> None:
            with self._lock:
                session.abort_provider = callback
                should_abort = cancel.is_set()
            if should_abort:
                callback()

        def produce() -> None:
            trace_id: str | None = None
            context_token = pipeline.set_generation_sink(emit_token, cancel, register_abort)
            try:
                execution = execute_agent(
                    graph, traces, session.user_id, text, memory,
                    thread_id=session.session_id,
                )
                trace_id = execution.trace_id
                if execution.error:
                    emit_token(execution.error)
                elif execution.answer:
                    with self._lock:
                        streamed_text = next(
                            item["text"] for item in session.messages
                            if item["message_id"] == message_id
                        )
                    if not streamed_text:
                        emit_token(execution.answer)
                with self._lock:
                    interrupted = cancel.is_set()
                    message = next(
                        item for item in session.messages
                        if item["message_id"] == message_id
                    )
                    if not interrupted:
                        message["status"] = "completed"
                        message["trace_id"] = trace_id
                        session.status = "active"
                    self._persist(session)
                if not interrupted:
                    self.publish(session.session_id, {
                        "event": "generation_completed",
                        "data": {"session_id": session.session_id,
                                 "message_id": message_id,
                                 "generation_id": generation_id},
                    })
            except (AgentExecutionError, InterruptedError):
                with self._lock:
                    interrupted = cancel.is_set()
                    message = next(
                        item for item in session.messages
                        if item["message_id"] == message_id
                    )
                    if interrupted:
                        message["status"] = "interrupted"
                        session.status = "interrupted"
                    else:
                        message["text"] = "No he podido completar la respuesta. Inténtalo de nuevo."
                        message["status"] = "completed"
                        session.status = "active"
                    self._persist(session)
                if interrupted:
                    self.publish(session.session_id, {
                        "event": "generation_interrupted",
                        "data": {"session_id": session.session_id,
                                 "message_id": message_id, "status": "interrupted",
                                 "generation_id": generation_id},
                    })
                else:
                    self.publish(session.session_id, {
                        "event": "generation_completed",
                        "data": {"session_id": session.session_id,
                                 "message_id": message_id,
                                 "generation_id": generation_id},
                    })
            except Exception:
                with self._lock:
                    interrupted = cancel.is_set()
                    message = next(
                        item for item in session.messages
                        if item["message_id"] == message_id
                    )
                    message["status"] = "interrupted" if interrupted else "completed"
                    if not interrupted:
                        message["text"] = "No he podido completar la respuesta. Inténtalo de nuevo."
                        session.status = "active"
                    self._persist(session)
                self.publish(session.session_id, {
                    "event": "generation_interrupted" if interrupted else "generation_completed",
                    "data": {"session_id": session.session_id,
                             "message_id": message_id,
                             "status": "interrupted" if interrupted else "completed",
                             "generation_id": generation_id},
                })
            finally:
                pipeline.reset_generation_sink(context_token)
                with self._lock:
                    if session.generation_id == generation_id:
                        session.abort_provider = None
                        session.cancelled = None

        session.future = self._executor.submit(produce)

    def interrupt(self, session: ChatSession, new_input: str) -> None:
        with self._lock:
            cancelled = session.cancelled
            abort = session.abort_provider
            message = next(
                (item for item in reversed(session.messages)
                 if item.get("role") == "assistant" and item.get("status") == "streaming"),
                None,
            )
            generation_id = session.generation_id
            if cancelled is not None:
                cancelled.set()
            if message is not None:
                message["status"] = "interrupted"
            session.status = "interrupted"
            self._persist(session)
        if abort is not None:
            try:
                abort()
            except Exception:
                # Cancellation state is authoritative; provider close is best-effort.
                pass
        self.publish(session.session_id, {
            "event": "interrupt_requested",
            "data": {"session_id": session.session_id, "new_input": new_input},
        })
        # The producer emits generation_interrupted after the provider stream
        # has actually stopped, preventing a terminal event from claiming an abort
        # before cancellation has taken effect.

    async def wait_for_interruption(self, session: ChatSession) -> None:
        """Wait until the cancelled producer releases the LangGraph thread."""
        future = session.future
        if future is not None:
            await asyncio.to_thread(future.result)

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)


def resolve_client_id(user: dict[str, Any]) -> str:
    """Bind B2B users to their existing tenant identity; consumers default to user ID."""
    return str(user.get("client_id") or user["id"])
