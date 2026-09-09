"""Pruebas unitarias de las decisiones de negocio de incidencias."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from incidents.models import IncidentCreate, IncidentResponse, IncidentStatusUpdate
from routes import incidents


def _incident_response(incident_id: int = 1) -> IncidentResponse:
    return IncidentResponse(id=incident_id, title="Retraso de entrega", description="La entrega necesita seguimiento.", category="tracking", status="open", origin="customer", branch="zaragoza", created_at="2026-09-09T00:00:00+00:00", updated_at="2026-09-09T00:00:00+00:00")


class _IncidentRepository:
    def __init__(self, result: IncidentResponse | None | Exception) -> None:
        self.result = result
        self.filters = None

    def create(self, payload: IncidentCreate) -> IncidentResponse:
        return self._result()

    def list(self, filters: object) -> list[IncidentResponse]:
        self.filters = filters
        return [self._result()]

    def get(self, incident_id: int) -> IncidentResponse | None:
        return self._result()

    def update_status(self, incident_id: int, status: str) -> IncidentResponse | None:
        return self._result()

    def _result(self) -> IncidentResponse | None:
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_create_incident_returns_created_incident(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(incidents, "get_incidents_repository", lambda: _IncidentRepository(_incident_response()))

    created = incidents.create_incident(IncidentCreate(title="Retraso de entrega", description="La entrega necesita seguimiento.", category="tracking", origin="customer", branch="zaragoza"))

    assert (created.id, created.status) == (1, "open")


def test_list_incidents_applies_optional_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    repository = _IncidentRepository(_incident_response())
    monkeypatch.setattr(incidents, "get_incidents_repository", lambda: repository)

    listed = incidents.list_incidents(status_param="open", origin="customer", branch="zaragoza", category="tracking")

    assert [incident.id for incident in listed] == [1]
    assert repository.filters.status == "open"
    assert repository.filters.category == "tracking"


def test_incident_routes_reject_missing_resource_and_invalid_transition(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(incidents, "get_incidents_repository", lambda: _IncidentRepository(None))
    with pytest.raises(HTTPException, match="ID 99") as missing:
        incidents.get_incident(99)
    assert missing.value.status_code == 404

    monkeypatch.setattr(incidents, "get_incidents_repository", lambda: _IncidentRepository(ValueError("Transicion no permitida")))
    with pytest.raises(HTTPException, match="Transicion no permitida") as invalid_transition:
        incidents.update_incident_status(1, IncidentStatusUpdate(status="resolved"))
    assert invalid_transition.value.status_code == 400