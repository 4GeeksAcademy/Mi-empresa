from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SupplierCountry(str, Enum):
    US = "US"
    ES = "ES"


class SupplierCategory(str, Enum):
    TRANSPORTE = "transporte"
    EMBALAJE = "embalaje"
    ALMACENAJE = "almacenaje"
    DEVOLUCIONES = "devoluciones"
    TECNOLOGIA = "tecnologia"


class SupplierStatus(str, Enum):
    ACTIVO = "activo"
    SUSPENDIDO = "suspendido"


class SupplierBase(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    pais: SupplierCountry
    categorias_producto: list[SupplierCategory] = Field(min_length=1)
    tarifa_por_kg: float = Field(gt=0)
    status: SupplierStatus

    @field_validator("nombre")
    @classmethod
    def validate_nombre(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("El nombre del proveedor no puede estar vacio.")
        return normalized


class SupplierCreateInput(SupplierBase):
    model_config = ConfigDict(extra="forbid")


class SupplierRateUpdateInput(BaseModel):
    tarifa_por_kg: float = Field(gt=0)


class SupplierStatusUpdateInput(BaseModel):
    status: SupplierStatus


class SupplierResponse(SupplierBase):
    id: int
    updated_at: str


class SupplierPersistence(SupplierBase):
    # Modelo interno para persistencia sin id (TinyDB usa doc_id).
    updated_at: str


class SupplierFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pais: SupplierCountry | None = None
    categoria: SupplierCategory | None = None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
