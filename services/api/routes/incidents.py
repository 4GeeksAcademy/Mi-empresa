from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from incidents.models import (
    IncidentCreate,
    IncidentFilters,
    IncidentResponse,
    IncidentStatusUpdate,
)
from incidents.repository import get_incidents_repository

router = APIRouter(prefix="/api/incidents", tags=["incidents"])


@router.post("", response_model=IncidentResponse, status_code=status.HTTP_201_CREATED)
def create_incident(payload: IncidentCreate) -> IncidentResponse:
    """Crea una nueva incidencia."""
    repo = get_incidents_repository()
    try:
        return repo.create(payload)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al crear la incidencia. Intentalo de nuevo mas tarde.",
        ) from exc


@router.get("", response_model=list[IncidentResponse])
def list_incidents(
    status_param: str | None = Query(default=None, alias="status"),
    origin: str | None = Query(default=None),
    branch: str | None = Query(default=None),
    category: str | None = Query(default=None),
) -> list[IncidentResponse]:
    """Devuelve la lista de incidencias con filtros opcionales."""
    try:
        filters = IncidentFilters(
            status=status_param,
            origin=origin,
            branch=branch,
            category=category,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    repo = get_incidents_repository()
    return repo.list(filters)


@router.get("/summary")
def get_summary() -> dict:
    """Devuelve metricas agregadas de incidencias."""
    repo = get_incidents_repository()
    try:
        return repo.get_summary()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al obtener el resumen. Intentalo de nuevo mas tarde.",
        ) from exc


@router.get("/{incident_id}", response_model=IncidentResponse)
def get_incident(incident_id: int) -> IncidentResponse:
    """Devuelve el detalle de una incidencia por ID."""
    repo = get_incidents_repository()
    incident = repo.get(incident_id)
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontro la incidencia con ID {incident_id}.",
        )
    return incident


@router.patch("/{incident_id}/status", response_model=IncidentResponse)
def update_incident_status(
    incident_id: int,
    payload: IncidentStatusUpdate,
) -> IncidentResponse:
    """Actualiza el estado de una incidencia validando transiciones."""
    repo = get_incidents_repository()
    try:
        updated = repo.update_status(incident_id, payload.status)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontro la incidencia con ID {incident_id}.",
        )

    return updated