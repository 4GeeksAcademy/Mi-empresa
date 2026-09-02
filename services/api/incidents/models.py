from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

ALLOWED_CATEGORIES_VALUES = [
    "logistica",
    "tracking",
    "devolucion",
    "facturacion",
    "soporte",
]

ALLOWED_STATUS_VALUES = [
    "open",
    "in_progress",
    "resolved",
    "discarded",
]

ALLOWED_ORIGIN_VALUES = [
    "customer",
    "branch",
    "internal",
]

ALLOWED_BRANCH_VALUES = [
    "los-angeles",
    "zaragoza",
    "central",
]

# Mapa de estados CSV (antiguo) -> nuevo modelo
STATUS_TRANSITION_MAP: dict[str, str] = {
    "abierto": "open",
    "en_progreso": "in_progress",
    "cerrado": "resolved",
    "descartado": "discarded",
}

# Transiciones de estado validas (ciclo de vida)
VALID_STATUS_TRANSITIONS: dict[str, list[str]] = {
    "open": ["in_progress", "discarded"],
    "in_progress": ["resolved", "discarded"],
    "resolved": [],
    "discarded": [],
}

CATEGORY_LABELS: dict[str, str] = {
    "logistica": "Logistica",
    "tracking": "Tracking",
    "devolucion": "Devolucion",
    "facturacion": "Facturacion",
    "soporte": "Soporte",
}

ORIGIN_LABELS: dict[str, str] = {
    "customer": "Cliente",
    "branch": "Sede",
    "internal": "Interno",
}

STATUS_LABELS: dict[str, str] = {
    "open": "Abierta",
    "in_progress": "En progreso",
    "resolved": "Resuelta",
    "discarded": "Descartada",
}

BRANCH_LABELS: dict[str, str] = {
    "los-angeles": "Los Angeles",
    "zaragoza": "Zaragoza",
    "central": "Central",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class IncidentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    category: str = Field(min_length=1)
    status: str = Field(default="open")
    origin: str = Field(min_length=1)
    branch: str = Field(min_length=1)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        v = value.strip()
        if not v:
            raise ValueError("El titulo es obligatorio y no puede estar vacio.")
        return v

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        v = value.strip()
        if not v:
            raise ValueError("La descripcion es obligatoria y no puede estar vacia.")
        return v

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str) -> str:
        v = value.strip().lower()
        if v not in ALLOWED_CATEGORIES_VALUES:
            raise ValueError(
                f"La categoria '{value}' no es valida. "
                f"Opciones permitidas: {', '.join(ALLOWED_CATEGORIES_VALUES)}."
            )
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        v = value.strip().lower()
        if v not in ALLOWED_STATUS_VALUES:
            raise ValueError(
                f"El estado '{value}' no es valido. "
                f"Opciones permitidas: {', '.join(ALLOWED_STATUS_VALUES)}."
            )
        return v

    @field_validator("origin")
    @classmethod
    def validate_origin(cls, value: str) -> str:
        v = value.strip().lower()
        if v not in ALLOWED_ORIGIN_VALUES:
            raise ValueError(
                f"El origen '{value}' no es valido. "
                f"Opciones permitidas: {', '.join(ALLOWED_ORIGIN_VALUES)}."
            )
        return v

    @field_validator("branch")
    @classmethod
    def validate_branch(cls, value: str) -> str:
        v = value.strip().lower()
        if v not in ALLOWED_BRANCH_VALUES:
            raise ValueError(
                f"La sede '{value}' no es valida. "
                f"Opciones permitidas: {', '.join(ALLOWED_BRANCH_VALUES)}."
            )
        return v


class IncidentStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = Field(min_length=1)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        v = value.strip().lower()
        if v not in ALLOWED_STATUS_VALUES:
            raise ValueError(
                f"El estado '{value}' no es valido. "
                f"Opciones permitidas: {', '.join(ALLOWED_STATUS_VALUES)}."
            )
        return v


class IncidentResponse(BaseModel):
    id: int
    title: str
    description: str
    category: str
    status: str
    origin: str
    branch: str
    created_at: str
    updated_at: str


class IncidentPersistence(BaseModel):
    """Modelo interno para persistencia en TinyDB (sin id, que usa doc_id)."""
    title: str
    description: str
    category: str
    status: str
    origin: str
    branch: str
    created_at: str
    updated_at: str


class IncidentFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str | None = None
    origin: str | None = None
    branch: str | None = None
    category: str | None = None