from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from tinydb import TinyDB, Query

from .models import (
    IncidentCreate,
    IncidentFilters,
    IncidentPersistence,
    IncidentResponse,
    IncidentStatusUpdate,
    VALID_STATUS_TRANSITIONS,
    utc_now_iso,
)

DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "incidents.json"


class IncidentRepository:
    def __init__(self, db_path: Path | None = None) -> None:
        path = db_path or DEFAULT_DB_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = TinyDB(path)
        self._table = self._db.table("incidents")
        self._id_table = self._db.table("incident_ids")  # Para idempotencia

    def _to_response(self, doc: Any) -> IncidentResponse:
        data = dict(doc)
        data["id"] = doc.doc_id
        return IncidentResponse.model_validate(data)

    def find_by_csv_id(self, csv_incident_id: str) -> bool:
        """Comprueba si un incident_id del CSV ya fue insertado (idempotencia)."""
        q = Query()
        result = self._id_table.search(q.csv_id == csv_incident_id)
        return len(result) > 0

    def mark_csv_id_inserted(self, csv_incident_id: str) -> None:
        """Marca un incident_id del CSV como ya insertado."""
        self._id_table.insert({"csv_id": csv_incident_id})

    def create(self, incident_input: IncidentCreate) -> IncidentResponse:
        now = utc_now_iso()
        payload = IncidentPersistence(
            title=incident_input.title,
            description=incident_input.description,
            category=incident_input.category,
            status=incident_input.status,
            origin=incident_input.origin,
            branch=incident_input.branch,
            created_at=now,
            updated_at=now,
        )
        doc_id = self._table.insert(payload.model_dump())
        created = self._table.get(doc_id=doc_id)
        if created is None:
            raise RuntimeError("No se pudo recuperar la incidencia recien insertada.")
        return self._to_response(created)

    def list(self, filters: IncidentFilters) -> list[IncidentResponse]:
        rows = [self._to_response(doc) for doc in self._table.all()]

        if filters.status is not None:
            rows = [row for row in rows if row.status == filters.status]
        if filters.origin is not None:
            rows = [row for row in rows if row.origin == filters.origin]
        if filters.branch is not None:
            rows = [row for row in rows if row.branch == filters.branch]
        if filters.category is not None:
            rows = [row for row in rows if row.category == filters.category]

        return rows

    def get(self, incident_id: int) -> IncidentResponse | None:
        doc = self._table.get(doc_id=incident_id)
        if doc is None:
            return None
        return self._to_response(doc)

    def update_status(
        self, incident_id: int, new_status: str
    ) -> IncidentResponse | None:
        existing = self._table.get(doc_id=incident_id)
        if existing is None:
            return None

        current_status = existing.get("status", "")
        allowed = VALID_STATUS_TRANSITIONS.get(current_status, [])
        if new_status not in allowed:
            raise ValueError(
                f"No se puede cambiar el estado de '{current_status}' a '{new_status}'. "
                f"Transiciones permitidas desde '{current_status}': {', '.join(allowed) if allowed else 'ninguna (estado final)'}."
            )

        self._table.update(
            {
                "status": new_status,
                "updated_at": utc_now_iso(),
            },
            doc_ids=[incident_id],
        )
        updated = self._table.get(doc_id=incident_id)
        if updated is None:
            return None
        return self._to_response(updated)

    def get_summary(self) -> dict[str, dict[str, int]]:
        rows = [dict(doc) for doc in self._table.all()]

        status_counter: Counter[str] = Counter()
        category_counter: Counter[str] = Counter()
        origin_counter: Counter[str] = Counter()
        branch_counter: Counter[str] = Counter()

        for row in rows:
            status_counter[row.get("status", "")] += 1
            category_counter[row.get("category", "")] += 1
            origin_counter[row.get("origin", "")] += 1
            branch_counter[row.get("branch", "")] += 1

        return {
            "total_incidents": len(rows),
            "by_status": dict(sorted(status_counter.items())),
            "by_category": dict(sorted(category_counter.items())),
            "by_origin": dict(sorted(origin_counter.items())),
            "by_branch": dict(sorted(branch_counter.items())),
        }


# Instancia singleton para compartir en la app
_repo_instance: IncidentRepository | None = None


def get_incidents_repository() -> IncidentRepository:
    global _repo_instance
    if _repo_instance is None:
        _repo_instance = IncidentRepository()
    return _repo_instance