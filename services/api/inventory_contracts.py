"""Inventory read contracts shared by the API and MCP without ORM dependencies."""

from enum import Enum

from pydantic import BaseModel


class Warehouse(str, Enum):
    LOS_ANGELES = "los_angeles"
    ZARAGOZA = "zaragoza"


class ProductResponse(BaseModel):
    id: int
    name: str
    sku: str
    warehouse: Warehouse
    current_stock: int
