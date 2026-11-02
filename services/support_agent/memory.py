"""Owner-scoped persistent memories and explicit user-consent workflow."""

import re
import sqlite3
import unicodedata
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from typing import Literal
from uuid import uuid4

MemoryCategory = Literal["carrier_rule", "incident_pattern", "b2b_report_preference"]
MemoryAction = Literal[
    "none", "approved", "rejected", "edited", "unrelated", "ambiguous", "expired",
]


@dataclass(frozen=True)
class MemoryDraft:
    category: MemoryCategory
    memory_key: str
    content: str


@dataclass(frozen=True)
class MemoryResolution:
    action: MemoryAction
    question: str | None
    proposal: dict[str, str] | None = None


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalized(value: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", value.casefold())
        if not unicodedata.combining(char)
    )


def _contains_forbidden_data(value: str) -> bool:
    text = _normalized(value)
    exact_address = re.search(
        r"\b(?:calle|avenida|av\.?|street|st\.?|road|rd\.?|"
        r"address|direccion)\s+[a-z0-9 .'-]{2,40}\s+\d{1,5}\b",
        text,
    )
    street_address = re.search(
        r"\b\d{1,5}\s+(?:[a-z0-9'.-]+\s+){0,5}"
        r"(?:street|st\.?|road|rd\.?|avenue|ave\.?|boulevard|blvd\.?|"
        r"drive|dr\.?|lane|ln\.?|court|ct\.?)\b",
        text,
    )
    postal_code = re.search(r"\b\d{5}(?:-\d{4})?\b", text)
    coordinates = re.search(r"\b-?\d{1,3}\.\d{4,}\s*,\s*-?\d{1,3}\.\d{4,}\b", text)
    internal_warehouse_route = re.search(
        r"\b(?:ruta|route|pasillo|aisle)\b.{0,50}"
        r"\b(?:interna?|interior|almacen|warehouse|bodega)\b"
        r"|\b(?:almacen|warehouse|bodega)\b.{0,50}"
        r"\b(?:ruta|route|pasillo|aisle)\b",
        text,
    )
    active_negotiation = re.search(
        r"\b(?:negociacion activa|en negociacion|negociando|"
        r"contrato.{0,30}negociacion|negociacion.{0,30}contrato)\b",
        text,
    )
    tracking_identifier = re.search(
        r"\b(?:tracking|seguimiento|paquete|pedido)\s*(?:id|#|:)?\s*"
        r"[a-z0-9-]*\d[a-z0-9-]{2,}\b",
        text,
    )
    return any((
        exact_address, street_address, postal_code, coordinates, internal_warehouse_route,
        active_negotiation, tracking_identifier,
    ))


def _valid_draft(draft: MemoryDraft) -> bool:
    return (
        draft.category in {
            "carrier_rule", "incident_pattern", "b2b_report_preference",
        }
        and 1 <= len(draft.memory_key) <= 120
        and 1 <= len(draft.content) <= 320
        and not _contains_forbidden_data(draft.content)
        and not _contains_forbidden_data(draft.memory_key)
    )


def propose_memory(message: str) -> MemoryDraft | None:
    """Extract only the small set of recurring facts allowed by the briefing."""
    text = _normalized(message)
    if _contains_forbidden_data(message):
        return None

    if (
        re.search(r"\b(?:reporte|informe)\b", text)
        and re.search(r"\bmensual\b", text)
        and re.search(r"\b(?:siempre|prefiere|prefieren|quiere|solicita)\b", text)
        and re.search(r"\b(?:cliente|marca|b2b)\b", text)
    ):
        segment = (
            "cosmetics" if re.search(r"\b(?:cosmetica|cosmeticos)\b", text)
            else "b2b-clients"
        )
        preferences: list[str] = []
        if re.search(r"\b(?:en|formato)\s+pdf\b", text):
            preferences.append("formato PDF")
        if re.search(
            r"\bdevoluciones\b.{0,80}\bantes\b.{0,40}\b(?:envios|volumen)\b",
            text,
        ):
            preferences.append("devoluciones antes que volumen de envíos")
        elif re.search(
            r"\b(?:envios|volumen)\b.{0,80}\bantes\b.{0,40}\bdevoluciones\b",
            text,
        ):
            preferences.append("volumen de envíos antes que devoluciones")
        if not preferences:
            return None
        draft = MemoryDraft(
            "b2b_report_preference",
            f"b2b-report:{segment}",
            f"Para clientes B2B de {segment}, preferencias del reporte mensual: "
            + "; ".join(preferences) + ".",
        )
        return draft if _valid_draft(draft) else None

    carrier = next((name for name, pattern in (
        ("SEUR", r"\bseur\b"),
        ("MRW", r"\bmrw\b"),
        ("UPS", r"\bups\b"),
        ("FedEx", r"\bfedex\b"),
        ("DHL", r"\bdhl\b"),
        ("carrier local", r"\bcarrier local\b|\btransportista local\b"),
    ) if re.search(pattern, text)), None)
    correction = re.search(
        r"\b(?:ya no cubre|dejo de cubrir|no cubre|cambio su cobertura|"
        r"cambio la cobertura|dejo de operar|ya no opera|no opera)\b",
        text,
    )
    place = (
        ("ES", "Zaragoza")
        if re.search(r"\bzaragoza\b", text)
        else ("ES", "España")
        if re.search(r"\b(?:espana|spain)\b", text)
        else ("US", "Los Ángeles")
        if re.search(r"\blos angeles\b", text)
        else ("US", "Estados Unidos")
        if re.search(r"\b(?:usa|united states)\b", text)
        else None
    )
    if carrier and correction and place:
        country, city = place
        rural = bool(re.search(r"\b(?:rural|rurales)\b", text))
        area = f"zonas rurales de {city}" if rural else city
        replacement = bool(re.search(
            r"\b(?:carrier local|transportista local)\b", text,
        ))
        if re.search(
            r"\b(?:ya no cubre|dejo de cubrir|no cubre|dejo de operar|"
            r"ya no opera|no opera)\b",
            text,
        ):
            content = (
                f"{carrier} ya no cubre {area}; "
                f"{'usar el carrier local' if replacement else 'confirmar un carrier alternativo'}."
            )
        else:
            content = message.strip()
        region = f"{country}:{city.casefold().replace(' ', '-')}"
        key = f"carrier:{carrier.casefold()}:{region}:{'rural' if rural else 'general'}"
        draft = MemoryDraft("carrier_rule", key, content)
        return draft if _valid_draft(draft) else None

    recurring = re.search(
        r"\b(?:tres|varios|varias|recurrente|repetid[oa]s?|"
        r"multiples|mas de un|mas de una)\b",
        text,
    )
    delay = re.search(r"\b(?:retrasos?|demoras?)\b", text)
    cause = re.search(r"\b(?:huelga|strike)\b", text)
    if recurring and delay and cause and place:
        country, city = place
        location = "portuaria" if re.search(r"\b(?:portuaria|puerto|port)\b", text) else "de transportistas"
        draft = MemoryDraft(
            "incident_pattern",
            f"incident:{country}:{city.casefold().replace(' ', '-')}:carrier-strike",
            f"Patrón recurrente de retrasos en {city} asociado a huelga {location}; "
            "no escalar como fallo interno sin nueva evidencia.",
        )
        return draft if _valid_draft(draft) else None

    return None


def _proposal_payload(row: sqlite3.Row) -> dict[str, str]:
    return {
        "id": row["proposal_id"],
        "tipo": row["category"],
        "clave": row["memory_key"],
        "contenido": row["content"],
        "pregunta": "¿Quieres que lo recuerde? Responde aprobar, rechazar o editar.",
    }


def _strip_connector(value: str) -> str:
    return re.sub(
        r"^[\s,.;:!?-]*(?:(?:y|and|ademas|además|also|pero|but)\b"
        r"[\s,.;:!?-]*)*",
        "",
        value,
        flags=re.IGNORECASE,
    ).strip()


def _classify_message(message: str) -> tuple[MemoryAction, str | None, str | None]:
    normalized = _normalized(message).strip()
    edit = re.match(
        r"^(?:edita(?:r)?|cambia(?:r)?|modifica(?:r)?|corrige(?:ir)?|"
        r"actualiza(?:r)?)(?:\s+(?:la\s+)?propuesta)?\s*(?::|a|por)?\s*(.+)$",
        message.strip(),
        flags=re.IGNORECASE,
    )
    if edit:
        return "edited", None, edit.group(1).strip()

    explicit_rejection = re.search(
        r"\b(?:no\s+(?:la|lo)\s+guardes|no\s+quiero\s+(?:guardarla|guardarlo|"
        r"que\s+la\s+guardes|que\s+lo\s+guardes)|no\s+lo\s+recuerdes)\b",
        message.strip(),
        flags=re.IGNORECASE,
    )
    if explicit_rejection:
        remainder = message[explicit_rejection.end():]
        remainder = _strip_connector(remainder)
        return "rejected", remainder or None, None

    rejection = re.match(
        r"^(?:(?:rechazo|rechazar|descarto|no\s+la\s+guardes|no\s+lo\s+recuerdes|"
        r"no\s+quiero\s+(?:guardarla|recordarlo))\b|no(?=$|[,!?.;:]))"
        r"[,!?.;:]*\s*(.*)$",
        message.strip(),
        flags=re.IGNORECASE,
    )
    if rejection:
        remainder = _strip_connector(rejection.group(1))
        return "rejected", remainder or None, None

    if re.search(
        r"\b(?:no estoy segur[oa]|no se|no lo se|quizas|tal vez|"
        r"maybe|not sure|uncertain)\b",
        normalized,
    ):
        return "ambiguous", None, None

    approval = re.match(
        r"^(?:s[ií]|yes|vale|ok|de acuerdo|apruebo|aprobar|confirmo|acepto|"
        r"guárdala|guárdalo|guardala|guardalo|guarda(?:la|lo)?)"
        r"(?:\b|[,!?.;:])\s*(.*)$",
        message.strip(),
        flags=re.IGNORECASE,
    )
    if approval:
        remainder = _strip_connector(approval.group(1))
        return "approved", remainder or None, None

    if "?" in message or re.search(
        r"\b(?:donde|que|cual|como|cuando|quien|why|where|what|which|how|when)\b",
        normalized,
    ):
        return "unrelated", message.strip(), None
    return "ambiguous", None, None


def _edited_draft(
    pending: sqlite3.Row,
    edit_text: str | None,
) -> MemoryDraft | None:
    if not edit_text:
        return None
    draft = propose_memory(edit_text)
    if draft is None or draft.category != pending["category"]:
        return None
    return draft


class AgentMemoryStore:
    """SQLite memory store separated from LangGraph checkpoints and RAG."""

    SHARED_MEMORY_OWNER = "trackflow"
    PROPOSAL_TTL = timedelta(minutes=30)
    MAX_MEMORIES_PER_OWNER = 100
    MEMORY_TTL_DAYS = {
        "carrier_rule": 180,
        "incident_pattern": 30,
        "b2b_report_preference": 365,
    }
    AUDIT_TTL_DAYS = 365

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self._lock = RLock()

    def _connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def _connection(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        with self._lock:
            connection = self._connect()
            try:
                if write:
                    connection.execute("BEGIN IMMEDIATE")
                yield connection
                if write:
                    connection.commit()
            except Exception:
                if write:
                    connection.rollback()
                raise
            finally:
                connection.close()

    def setup(self) -> None:
        with self._connection(write=True) as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS agent_memories (
                    memory_id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    memory_key TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_used_at TEXT NOT NULL,
                    UNIQUE(owner_id, category, memory_key)
                )
            """)
            connection.execute("""
                CREATE INDEX IF NOT EXISTS idx_agent_memories_owner_updated
                ON agent_memories(owner_id, updated_at DESC)
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS agent_memory_proposals (
                    proposal_id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    memory_key TEXT NOT NULL,
                    content TEXT NOT NULL,
                    status TEXT NOT NULL,
                    decision TEXT,
                    result TEXT,
                    source_proposal_id TEXT,
                    created_at TEXT NOT NULL,
                    decided_at TEXT,
                    FOREIGN KEY(source_proposal_id)
                        REFERENCES agent_memory_proposals(proposal_id)
                )
            """)
            connection.execute("""
                CREATE INDEX IF NOT EXISTS idx_agent_memory_proposals_owner_created
                ON agent_memory_proposals(owner_id, created_at DESC)
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS agent_memory_proposal_events (
                    event_id TEXT PRIMARY KEY,
                    proposal_id TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    result TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(proposal_id)
                        REFERENCES agent_memory_proposals(proposal_id)
                )
            """)
            pending_index = connection.execute(
                """SELECT sql FROM sqlite_master
                   WHERE type = 'index' AND name = 'idx_agent_memory_one_pending'"""
            ).fetchone()
            normalized_index = (
                " ".join(pending_index["sql"].upper().split())
                if pending_index is not None
                else ""
            )
            if pending_index is not None and (
                "ON AGENT_MEMORY_PROPOSALS(STATUS)" not in normalized_index
            ):
                connection.execute(
                    "DROP INDEX idx_agent_memory_one_pending"
                )
            pending_rows = connection.execute(
                """SELECT proposal_id, owner_id FROM agent_memory_proposals
                   WHERE status = 'pending' ORDER BY created_at, proposal_id"""
            ).fetchall()
            now = _timestamp()
            for row in pending_rows[1:]:
                result = "discarded_during_global_pending_limit_migration"
                connection.execute(
                    """UPDATE agent_memory_proposals
                       SET status = 'discarded', decision = 'discarded',
                           result = ?, decided_at = ?
                       WHERE proposal_id = ? AND status = 'pending'""",
                    (result, now, row["proposal_id"]),
                )
                connection.execute(
                    """INSERT INTO agent_memory_proposal_events
                       (event_id, proposal_id, owner_id, action, result, created_at)
                       VALUES (?, ?, ?, 'discarded_migration', ?, ?)""",
                    (
                        str(uuid4()), row["proposal_id"], row["owner_id"],
                        result, now,
                    ),
                )
            connection.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_memory_one_pending
                ON agent_memory_proposals(status) WHERE status = 'pending'
            """)
            self._expire_pending(connection, now)

    def _expire_pending(
        self, connection: sqlite3.Connection, now: str,
    ) -> set[str]:
        cutoff = datetime.fromisoformat(now) - self.PROPOSAL_TTL
        pending = connection.execute(
            """SELECT proposal_id, owner_id, created_at
               FROM agent_memory_proposals WHERE status = 'pending'"""
        ).fetchall()
        expired_owners: set[str] = set()
        for row in pending:
            if datetime.fromisoformat(row["created_at"]) > cutoff:
                continue
            result = "expired_without_confirmation_memory_unchanged"
            connection.execute(
                """UPDATE agent_memory_proposals
                   SET status = 'discarded', decision = 'expired',
                       result = ?, decided_at = ?
                   WHERE proposal_id = ? AND status = 'pending'""",
                (result, now, row["proposal_id"]),
            )
            connection.execute(
                """INSERT INTO agent_memory_proposal_events
                   (event_id, proposal_id, owner_id, action, result, created_at)
                   VALUES (?, ?, ?, 'expired', ?, ?)""",
                (
                    str(uuid4()), row["proposal_id"], row["owner_id"],
                    result, now,
                ),
            )
            expired_owners.add(row["owner_id"])
        return expired_owners

    def propose(self, owner_id: str, draft: MemoryDraft) -> dict[str, str] | None:
        if not _valid_draft(draft):
            return None
        now = _timestamp()
        proposal_id = str(uuid4())
        with self._connection(write=True) as connection:
            self._expire_pending(connection, now)
            pending = connection.execute(
                """SELECT * FROM agent_memory_proposals
                   WHERE status = 'pending' LIMIT 1"""
            ).fetchone()
            if pending is not None:
                return (
                    _proposal_payload(pending)
                    if pending["owner_id"] == owner_id
                    else None
                )
            connection.execute(
                """INSERT INTO agent_memory_proposals
                   (proposal_id, owner_id, category, memory_key, content, status, created_at)
                   VALUES (?, ?, ?, ?, ?, 'pending', ?)""",
                (
                    proposal_id, owner_id, draft.category, draft.memory_key,
                    draft.content, now,
                ),
            )
            connection.execute(
                """INSERT INTO agent_memory_proposal_events
                   (event_id, proposal_id, owner_id, action, result, created_at)
                   VALUES (?, ?, ?, 'proposed', 'awaiting_user_decision', ?)""",
                (str(uuid4()), proposal_id, owner_id, now),
            )
            row = connection.execute(
                "SELECT * FROM agent_memory_proposals WHERE proposal_id = ?",
                (proposal_id,),
            ).fetchone()
            if row is None:
                raise LookupError("Memory proposal was not persisted.")
            return _proposal_payload(row)

    def resolve_pending(self, owner_id: str, message: str) -> MemoryResolution:
        with self._connection(write=True) as connection:
            now = _timestamp()
            expired_owners = self._expire_pending(connection, now)
            if owner_id in expired_owners:
                return MemoryResolution("expired", message)
            pending = connection.execute(
                """SELECT * FROM agent_memory_proposals
                   WHERE owner_id = ? AND status = 'pending'""",
                (owner_id,),
            ).fetchone()
            if pending is None:
                return MemoryResolution("none", message)

            action, remainder, edit_text = _classify_message(message)
            result = "no_memory_change"
            proposal: dict[str, str] | None = None
            final_action = action

            if action == "approved":
                draft = MemoryDraft(
                    pending["category"], pending["memory_key"], pending["content"],
                )
                if not _valid_draft(draft):
                    raise ValueError("Pending memory proposal failed policy validation.")
                connection.execute(
                    """INSERT INTO agent_memories
                       (memory_id, owner_id, category, memory_key, content,
                        created_at, updated_at, last_used_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(owner_id, category, memory_key) DO UPDATE SET
                           content = excluded.content,
                           updated_at = excluded.updated_at,
                           last_used_at = excluded.last_used_at""",
                    (
                        str(uuid4()), self.SHARED_MEMORY_OWNER,
                        draft.category, draft.memory_key,
                        draft.content, now, now, now,
                    ),
                )
                self._consolidate(connection, self.SHARED_MEMORY_OWNER, now)
                result = "approved_memory_consolidated"
            elif action == "rejected":
                result = "rejected_memory_unchanged"
            elif action == "unrelated":
                result = "discarded_after_topic_change"
            elif action == "edited":
                replacement = _edited_draft(pending, edit_text)
                if replacement is None or not _valid_draft(replacement):
                    action = "rejected"
                    final_action = "rejected"
                    remainder = edit_text or message.strip() or None
                    result = "invalid_edit_default_rejected_memory_unchanged"
                else:
                    replacement_id = str(uuid4())
                    result = "edited_proposal_replaced_pending_confirmation"
                    connection.execute(
                        """UPDATE agent_memory_proposals
                           SET status = 'edited', decision = 'edited', result = ?,
                               decided_at = ?
                           WHERE proposal_id = ? AND status = 'pending'""",
                        (result, now, pending["proposal_id"]),
                    )
                    connection.execute(
                        """INSERT INTO agent_memory_proposals
                           (proposal_id, owner_id, category, memory_key, content,
                            status, source_proposal_id, created_at)
                           VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)""",
                        (
                            replacement_id, owner_id, replacement.category,
                            replacement.memory_key, replacement.content,
                            pending["proposal_id"], now,
                        ),
                    )
                    replacement_row = connection.execute(
                        "SELECT * FROM agent_memory_proposals WHERE proposal_id = ?",
                        (replacement_id,),
                    ).fetchone()
                    if replacement_row is None:
                        raise LookupError("Edited memory proposal was not persisted.")
                    proposal = _proposal_payload(replacement_row)
                    connection.execute(
                        """INSERT INTO agent_memory_proposal_events
                           (event_id, proposal_id, owner_id, action, result, created_at)
                           VALUES (?, ?, ?, 'proposed', 'awaiting_user_decision', ?)""",
                        (str(uuid4()), replacement_id, owner_id, now),
                    )
            elif action == "ambiguous":
                action = "rejected"
                final_action = "rejected"
                remainder = message.strip() or None
                result = "ambiguous_default_rejected_memory_unchanged"

            if action in {"approved", "rejected", "unrelated"} or (
                action == "edited" and final_action == "edited"
            ):
                status = {
                    "approved": "approved",
                    "rejected": "rejected",
                    "unrelated": "discarded",
                    "edited": "edited",
                }[action]
                connection.execute(
                    """UPDATE agent_memory_proposals
                       SET status = ?, decision = ?, result = ?, decided_at = ?
                       WHERE proposal_id = ? AND status = 'pending'""",
                    (status, action, result, now, pending["proposal_id"]),
                )
            connection.execute(
                """INSERT INTO agent_memory_proposal_events
                   (event_id, proposal_id, owner_id, action, result, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    str(uuid4()), pending["proposal_id"], owner_id,
                    (
                        "ambiguous_rejected"
                        if result == "ambiguous_default_rejected_memory_unchanged"
                        else "invalid_edit_rejected"
                        if result == "invalid_edit_default_rejected_memory_unchanged"
                        else action if final_action == action else "edit_rejected"
                    ),
                    result, now,
                ),
            )

            if final_action == "ambiguous":
                proposal = _proposal_payload(pending)
            if action in {"approved", "rejected", "unrelated"}:
                final_question = remainder
            else:
                final_question = None
            return MemoryResolution(final_action, final_question, proposal)

    def list_memories(self) -> list[dict[str, str]]:
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT category, memory_key, content, created_at, updated_at
                   FROM agent_memories WHERE owner_id = ?
                   ORDER BY updated_at DESC""",
                (self.SHARED_MEMORY_OWNER,),
            ).fetchall()
        return [dict(row) for row in rows]

    def consolidate(self) -> dict[str, int]:
        now = _timestamp()
        with self._connection(write=True) as connection:
            self._expire_pending(connection, now)
            before = connection.execute(
                "SELECT COUNT(*) AS count FROM agent_memories WHERE owner_id = ?",
                (self.SHARED_MEMORY_OWNER,),
            ).fetchone()["count"]
            self._consolidate(connection, self.SHARED_MEMORY_OWNER, now)
            after = connection.execute(
                "SELECT COUNT(*) AS count FROM agent_memories WHERE owner_id = ?",
                (self.SHARED_MEMORY_OWNER,),
            ).fetchone()["count"]
        return {"memories_removed": before - after}

    def list_audit(
        self, owner_id: str,
    ) -> dict[str, list[dict[str, str | None]]]:
        with self._connection(write=True) as connection:
            self._expire_pending(connection, _timestamp())
            rows = connection.execute(
                """SELECT proposal_id, category, memory_key, content, status,
                          decision, result, created_at, decided_at
                   FROM agent_memory_proposals WHERE owner_id = ?
                   ORDER BY created_at DESC LIMIT 200""",
                (owner_id,),
            ).fetchall()
            events = connection.execute(
                """SELECT proposal_id, action, result, created_at
                   FROM agent_memory_proposal_events WHERE owner_id = ?
                   ORDER BY created_at DESC LIMIT 500""",
                (owner_id,),
            ).fetchall()
        return {
            "proposals": [dict(row) for row in rows],
            "events": [dict(row) for row in events],
        }

    def relevant_memories(self, question: str) -> list[dict[str, str]]:
        ignored = {
            "para", "como", "desde", "donde", "cuando", "sobre", "entre",
            "this", "that", "with", "from", "what", "where", "when",
            "the", "and", "for", "una", "uno", "las", "los", "del",
        }
        words = {
            word for word in re.findall(r"\b[\w-]{3,}\b", _normalized(question))
            if word not in ignored
        }
        if not words:
            return []
        with self._connection(write=True) as connection:
            rows = connection.execute(
                """SELECT category, memory_key, content, updated_at
                   FROM agent_memories WHERE owner_id = ?""",
                (self.SHARED_MEMORY_OWNER,),
            ).fetchall()
            ranked: list[tuple[int, sqlite3.Row]] = []
            for row in rows:
                memory_words = set(re.findall(
                    r"\b[\w-]{3,}\b",
                    _normalized(f"{row['memory_key']} {row['content']} {row['category']}"),
                ))
                overlap = len(words & memory_words)
                if overlap >= 2:
                    ranked.append((overlap, row))
            ranked.sort(key=lambda item: (item[0], item[1]["updated_at"]), reverse=True)
            selected = ranked[:3]
            now = _timestamp()
            for _, row in selected:
                connection.execute(
                    """UPDATE agent_memories SET last_used_at = ?
                       WHERE owner_id = ? AND category = ? AND memory_key = ?""",
                    (
                        now, self.SHARED_MEMORY_OWNER,
                        row["category"], row["memory_key"],
                    ),
                )
        return [
            {
                "category": row["category"],
                "content": row["content"],
                "updated_at": row["updated_at"],
            }
            for _, row in selected
        ]

    def _consolidate(
        self, connection: sqlite3.Connection, owner_id: str, now: str,
    ) -> None:
        current = datetime.fromisoformat(now)
        for category, days in self.MEMORY_TTL_DAYS.items():
            cutoff = (current - timedelta(days=days)).isoformat()
            connection.execute(
                """DELETE FROM agent_memories
                   WHERE owner_id = ? AND category = ? AND updated_at < ?""",
                (owner_id, category, cutoff),
            )
        connection.execute(
            """DELETE FROM agent_memories WHERE memory_id IN (
                   SELECT memory_id FROM agent_memories
                   WHERE owner_id = ?
                   ORDER BY last_used_at DESC, updated_at DESC
                   LIMIT -1 OFFSET ?
               )""",
            (owner_id, self.MAX_MEMORIES_PER_OWNER),
        )
        audit_cutoff = (current - timedelta(days=self.AUDIT_TTL_DAYS)).isoformat()
        connection.execute(
            """DELETE FROM agent_memory_proposal_events
               WHERE owner_id = ? AND proposal_id IN (
                   SELECT proposal_id FROM agent_memory_proposals
                   WHERE owner_id = ? AND status != 'pending' AND created_at < ?
                     AND NOT EXISTS (
                         SELECT 1 FROM agent_memory_proposals child
                         WHERE child.source_proposal_id =
                               agent_memory_proposals.proposal_id
                     )
               )""",
            (owner_id, owner_id, audit_cutoff),
        )
        connection.execute(
            """DELETE FROM agent_memory_proposals
               WHERE owner_id = ? AND status != 'pending' AND created_at < ?
                 AND NOT EXISTS (
                     SELECT 1 FROM agent_memory_proposals child
                     WHERE child.source_proposal_id =
                           agent_memory_proposals.proposal_id
                 )""",
            (owner_id, audit_cutoff),
        )
