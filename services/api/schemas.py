from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from models import Warehouse


class ProductCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    sku: str = Field(min_length=1, max_length=64)
    warehouse: Warehouse


class ProductResponse(BaseModel):
    id: int
    name: str
    sku: str
    warehouse: Warehouse
    current_stock: int


class InboundOrderCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: int
    quantity: int = Field(gt=0)


class OutboundOrderCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: int
    quantity: int = Field(gt=0)


class InventoryOrderResponse(BaseModel):
    id: int
    product_id: int
    product_name: str
    product_sku: str
    quantity: int
    direction: str
    created_at: datetime
    user_uuid: str
