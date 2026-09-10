from datetime import datetime, timezone
from enum import Enum
from typing import List

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import UniqueConstraint
from sqlmodel import Field as SQLField
from sqlmodel import Relationship, SQLModel


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


# --- Modelos ORM (SQLModel, table=True) para inventario en Supabase ---
# Separados semanticamente de los Pydantic de arriba: estas clases mapean tablas reales.


class Warehouse(str, Enum):
    LOS_ANGELES = "los_angeles"
    ZARAGOZA = "zaragoza"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Product(SQLModel, table=True):
    # Mismo SKU puede existir en ambos almacenes con stock independiente por particion.
    __table_args__ = (UniqueConstraint("sku", "warehouse", name="uq_product_sku_warehouse"),)

    id: int | None = SQLField(default=None, primary_key=True)
    name: str = SQLField(min_length=1, max_length=120)
    sku: str = SQLField(min_length=1, max_length=64, index=True)
    warehouse: Warehouse

    inbound_orders: List["InboundOrder"] = Relationship(back_populates="product")
    outbound_orders: List["OutboundOrder"] = Relationship(back_populates="product")


class InboundOrder(SQLModel, table=True):
    id: int | None = SQLField(default=None, primary_key=True)
    product_id: int = SQLField(foreign_key="product.id")
    quantity: int = SQLField(gt=0)
    created_at: datetime = SQLField(default_factory=utc_now)
    # Referencia al id de usuario de TinyDB (no hay tabla de usuarios en Supabase).
    user_uuid: str

    product: Product | None = Relationship(back_populates="inbound_orders")


class OutboundOrder(SQLModel, table=True):
    id: int | None = SQLField(default=None, primary_key=True)
    product_id: int = SQLField(foreign_key="product.id")
    quantity: int = SQLField(gt=0)
    created_at: datetime = SQLField(default_factory=utc_now)
    user_uuid: str

    product: Product | None = Relationship(back_populates="outbound_orders")
