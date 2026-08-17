from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from tinydb import Query, TinyDB

from models import (
    SupplierCategory,
    SupplierCountry,
    SupplierCreateInput,
    SupplierFilters,
    SupplierPersistence,
    SupplierResponse,
    SupplierStatus,
    utc_now_iso,
)

DEFAULT_DB_PATH = Path(__file__).resolve().parent / "data" / "suppliers.json"


class SupplierRepository:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = TinyDB(db_path)
        self._table = self._db.table("suppliers")

    def _to_response(self, doc: Any) -> SupplierResponse:
        data = dict(doc)
        data["id"] = doc.doc_id
        return SupplierResponse.model_validate(data)

    def list(self, filters: SupplierFilters) -> list[SupplierResponse]:
        rows = [self._to_response(doc) for doc in self._table.all()]

        if filters.pais is not None:
            rows = [row for row in rows if row.pais == filters.pais]

        if filters.categoria is not None:
            rows = [row for row in rows if filters.categoria in row.categorias_producto]

        return rows

    def get(self, supplier_id: int) -> SupplierResponse | None:
        doc = self._table.get(doc_id=supplier_id)
        if doc is None:
            return None
        return self._to_response(doc)

    def create(self, supplier_input: SupplierCreateInput) -> SupplierResponse:
        payload = SupplierPersistence(
            **supplier_input.model_dump(),
            updated_at=utc_now_iso(),
        )
        doc_id = self._table.insert(payload.model_dump())
        created = self._table.get(doc_id=doc_id)
        if created is None:
            raise RuntimeError("No se pudo recuperar el proveedor recien insertado.")
        return self._to_response(created)

    def update_rate(self, supplier_id: int, tarifa_por_kg: float) -> SupplierResponse | None:
        existing = self._table.get(doc_id=supplier_id)
        if existing is None:
            return None

        self._table.update(
            {
                "tarifa_por_kg": tarifa_por_kg,
                "updated_at": utc_now_iso(),
            },
            doc_ids=[supplier_id],
        )
        updated = self._table.get(doc_id=supplier_id)
        if updated is None:
            return None
        return self._to_response(updated)

    def update_status(self, supplier_id: int, status: SupplierStatus) -> SupplierResponse | None:
        existing = self._table.get(doc_id=supplier_id)
        if existing is None:
            return None

        self._table.update(
            {
                "status": status.value,
                "updated_at": utc_now_iso(),
            },
            doc_ids=[supplier_id],
        )
        updated = self._table.get(doc_id=supplier_id)
        if updated is None:
            return None
        return self._to_response(updated)

    def delete(self, supplier_id: int) -> bool:
        try:
            removed = self._table.remove(doc_ids=[supplier_id])
            return bool(removed)
        except KeyError:
            return False

    def find_by_name_and_country(self, nombre: str, pais: SupplierCountry) -> SupplierResponse | None:
        supplier = Query()
        doc = self._table.get((supplier.nombre == nombre) & (supplier.pais == pais.value))
        if doc is None:
            return None
        return self._to_response(doc)


def _resolve_db_path() -> Path:
    env_path = os.getenv("TRACKFLOW_SUPPLIERS_DB_PATH")
    if env_path:
        return Path(env_path)
    return DEFAULT_DB_PATH


@lru_cache
def get_suppliers_repository() -> SupplierRepository:
    return SupplierRepository(_resolve_db_path())


def get_seed_suppliers() -> list[SupplierCreateInput]:
    return [
        SupplierCreateInput(
            nombre="UPS",
            pais=SupplierCountry.US,
            categorias_producto=[SupplierCategory.TRANSPORTE],
            tarifa_por_kg=5.2,
            status=SupplierStatus.ACTIVO,
        ),
        SupplierCreateInput(
            nombre="FedEx",
            pais=SupplierCountry.US,
            categorias_producto=[SupplierCategory.TRANSPORTE],
            tarifa_por_kg=5.8,
            status=SupplierStatus.ACTIVO,
        ),
        SupplierCreateInput(
            nombre="DHL US",
            pais=SupplierCountry.US,
            categorias_producto=[SupplierCategory.TRANSPORTE],
            tarifa_por_kg=5.4,
            status=SupplierStatus.ACTIVO,
        ),
        SupplierCreateInput(
            nombre="MRW",
            pais=SupplierCountry.ES,
            categorias_producto=[SupplierCategory.TRANSPORTE],
            tarifa_por_kg=4.1,
            status=SupplierStatus.ACTIVO,
        ),
        SupplierCreateInput(
            nombre="SEUR",
            pais=SupplierCountry.ES,
            categorias_producto=[SupplierCategory.TRANSPORTE],
            tarifa_por_kg=4.3,
            status=SupplierStatus.ACTIVO,
        ),
        SupplierCreateInput(
            nombre="DHL ES",
            pais=SupplierCountry.ES,
            categorias_producto=[SupplierCategory.TRANSPORTE],
            tarifa_por_kg=4.7,
            status=SupplierStatus.ACTIVO,
        ),
        SupplierCreateInput(
            nombre="Paqueteria Oeste",
            pais=SupplierCountry.US,
            categorias_producto=[SupplierCategory.TRANSPORTE, SupplierCategory.DEVOLUCIONES],
            tarifa_por_kg=4.9,
            status=SupplierStatus.SUSPENDIDO,
        ),
        SupplierCreateInput(
            nombre="Iberia Express Local",
            pais=SupplierCountry.ES,
            categorias_producto=[SupplierCategory.TRANSPORTE, SupplierCategory.DEVOLUCIONES],
            tarifa_por_kg=3.9,
            status=SupplierStatus.ACTIVO,
        ),
    ]
