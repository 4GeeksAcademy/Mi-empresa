from datetime import datetime, timezone
from enum import Enum
from typing import List
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Column, Float, Index, JSON, Text, UniqueConstraint, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field as SQLField
from sqlmodel import Relationship, SQLModel

from inventory_contracts import Warehouse


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
    model_config = ConfigDict(extra="forbid")

    tarifa_por_kg: float = Field(gt=0)


class SupplierStatusUpdateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

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


class TelemetryEventRecord(SQLModel, table=True):
    __tablename__ = "telemetry_events"
    __table_args__ = (
        Index("ix_telemetry_events_timestamp", "timestamp"),
        Index("ix_telemetry_events_event_type", "event_type"),
        Index("ix_telemetry_events_tags_gin", "tags", postgresql_using="gin"),
    )

    id: UUID = SQLField(
        default_factory=uuid4,
        sa_column=Column(Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
    )
    timestamp: datetime
    service: str = SQLField(max_length=32)
    event_type: str = SQLField(max_length=100)
    level: str = SQLField(default="info", max_length=16)
    value: float | None = SQLField(default=None)
    message: str | None = SQLField(default=None, sa_type=Text)
    tags: dict = SQLField(
        default_factory=dict,
        sa_column=Column(
            JSON().with_variant(JSONB, "postgresql"),
            nullable=False,
            server_default=text("'{}'"),
        ),
    )


class RfpTicket(SQLModel, table=True):
    """Durable lifecycle record for an uploaded TrackFlow RFP."""

    __tablename__ = "rfp_tickets"
    __table_args__ = (Index("ix_rfp_tickets_owner_created", "owner_id", "created_at"),)

    ticket_id: UUID = SQLField(default_factory=uuid4, sa_column=Column(Uuid(as_uuid=True), primary_key=True))
    rfp_id: UUID = SQLField(default_factory=uuid4, sa_column=Column(Uuid(as_uuid=True), unique=True, nullable=False))
    owner_id: str = SQLField(max_length=64)
    original_filename: str = SQLField(max_length=255)
    raw_pdf_path: str = SQLField(sa_type=Text)
    markdown_path: str | None = SQLField(default=None, sa_type=Text)
    status: str = SQLField(default="analizando", max_length=32, index=True)
    classification_result: bool | None = None
    classification_reason: str | None = SQLField(default=None, sa_type=Text)
    processing_error: str | None = SQLField(default=None, sa_type=Text)
    synthesizer_payload: dict | None = SQLField(default=None, sa_column=Column(JSON().with_variant(JSONB, "postgresql")))
    # Parte 2: handoff de generación/evaluación hacia la Parte 3
    response_handoff: dict | None = SQLField(default=None, sa_column=Column(JSON().with_variant(JSONB, "postgresql")))
    created_at: datetime = SQLField(default_factory=utc_now)
    updated_at: datetime = SQLField(default_factory=utc_now)


class RfpMetadataRecord(SQLModel, table=True):
    __tablename__ = "rfp_metadata"

    ticket_id: UUID = SQLField(foreign_key="rfp_tickets.ticket_id", primary_key=True)
    client_name: str | None = SQLField(default=None, max_length=255)
    client_country: str | None = SQLField(default=None, max_length=80)
    services_requested: list[str] = SQLField(default_factory=list, sa_column=Column(JSON().with_variant(JSONB, "postgresql"), nullable=False))
    unknown_services: list[str] = SQLField(default_factory=list, sa_column=Column(JSON().with_variant(JSONB, "postgresql"), nullable=False))
    monthly_volume: int | None = None
    monthly_volume_unit: str | None = SQLField(default=None, max_length=80)
    deadline: str | None = SQLField(default=None, max_length=120)
    budget_range: str | None = SQLField(default=None, max_length=255)
    departments_needed: list[str] = SQLField(default_factory=list, sa_column=Column(JSON().with_variant(JSONB, "postgresql"), nullable=False))
    currency: str | None = SQLField(default=None, max_length=3)
    readability_metrics: dict = SQLField(default_factory=dict, sa_column=Column(JSON().with_variant(JSONB, "postgresql"), nullable=False))


class DepartmentSectionRecord(SQLModel, table=True):
    __tablename__ = "rfp_department_sections"
    __table_args__ = (UniqueConstraint("ticket_id", "department_id", name="uq_rfp_ticket_department"),)

    id: int | None = SQLField(default=None, primary_key=True)
    ticket_id: UUID = SQLField(foreign_key="rfp_tickets.ticket_id", index=True)
    department_id: str = SQLField(max_length=32)
    key_aspects: list[str] = SQLField(default_factory=list, sa_column=Column(JSON().with_variant(JSONB, "postgresql"), nullable=False))
    open_questions: list[str] = SQLField(default_factory=list, sa_column=Column(JSON().with_variant(JSONB, "postgresql"), nullable=False))
    source_extract: str = SQLField(default="", sa_type=Text)
    approver: str = SQLField(max_length=120)
    # Parte 2: borrador de la propuesta + resultado de evaluación estructurado
    draft_content: str | None = SQLField(default=None, sa_type=Text)
    evaluation_results: dict | None = SQLField(default=None, sa_column=Column(JSON().with_variant(JSONB, "postgresql")))
    approval_status: str = SQLField(default="pendiente", max_length=32)
    iteration_count: int = SQLField(default=0)
    needs_human_review: bool = SQLField(default=False)
    evaluated_at: datetime | None = SQLField(default=None)
    approved_at: datetime | None = SQLField(default=None)
    created_at: datetime = SQLField(default_factory=utc_now)
