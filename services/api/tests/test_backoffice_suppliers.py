"""Pruebas unitarias de las decisiones de negocio de proveedores."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from models import SupplierCategory, SupplierCreateInput, SupplierCountry, SupplierRateUpdateInput, SupplierResponse, SupplierStatus, SupplierStatusUpdateInput
from routes import suppliers


def _supplier_response(supplier_id: int = 1) -> SupplierResponse:
    return SupplierResponse(id=supplier_id, nombre="Proveedor Demo", pais=SupplierCountry.ES, categorias_producto=[SupplierCategory.TRANSPORTE], tarifa_por_kg=4.5, status=SupplierStatus.ACTIVO, updated_at="2026-09-09T00:00:00+00:00")


class _SupplierRepository:
    def __init__(self, result: SupplierResponse | None | Exception) -> None:
        self.result = result
        self.filters = None

    def create(self, payload: SupplierCreateInput) -> SupplierResponse:
        return self._result()

    def list(self, filters: object) -> list[SupplierResponse]:
        self.filters = filters
        return [self._result()]

    def update_status(self, supplier_id: int, status: SupplierStatus) -> SupplierResponse | None:
        return self._result()

    def update_rate(self, supplier_id: int, rate: float) -> SupplierResponse | None:
        return self._result()

    def get(self, supplier_id: int) -> SupplierResponse | None:
        return self._result()

    def delete(self, supplier_id: int) -> bool:
        result = self._result()
        return result is not None

    def _result(self) -> SupplierResponse | None:
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_create_supplier_returns_repository_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(suppliers, "get_suppliers_repository", lambda: _SupplierRepository(_supplier_response()))

    created = suppliers.create_supplier(SupplierCreateInput(nombre="Proveedor Demo", pais=SupplierCountry.ES, categorias_producto=[SupplierCategory.TRANSPORTE], tarifa_por_kg=4.5, status=SupplierStatus.ACTIVO), {"id": 1})

    assert (created.id, created.nombre) == (1, "Proveedor Demo")


def test_list_suppliers_uses_english_aliases_and_returns_matches(monkeypatch: pytest.MonkeyPatch) -> None:
    repository = _SupplierRepository(_supplier_response())
    monkeypatch.setattr(suppliers, "get_suppliers_repository", lambda: repository)

    listed = suppliers.list_suppliers(
        pais=None,
        categoria=None,
        country=SupplierCountry.ES,
        category=SupplierCategory.TRANSPORTE,
    )

    assert [supplier.id for supplier in listed] == [1]
    assert repository.filters.pais == SupplierCountry.ES
    assert repository.filters.categoria == SupplierCategory.TRANSPORTE


def test_supplier_routes_reject_missing_resource_and_wrap_repository_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(suppliers, "get_suppliers_repository", lambda: _SupplierRepository(None))
    with pytest.raises(HTTPException, match="Proveedor no encontrado") as missing:
        suppliers.update_supplier_status(99, SupplierStatusUpdateInput(status=SupplierStatus.SUSPENDIDO), {"id": 1})
    assert missing.value.status_code == 404

    monkeypatch.setattr(suppliers, "get_suppliers_repository", lambda: _SupplierRepository(RuntimeError("database unavailable")))
    with pytest.raises(HTTPException, match="Error interno al listar") as failed:
        suppliers.list_suppliers(pais=None, categoria=None, country=None, category=None)
    assert failed.value.status_code == 500


def test_supplier_routes_return_existing_resource_and_wrap_delete_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(suppliers, "get_suppliers_repository", lambda: _SupplierRepository(_supplier_response()))

    fetched = suppliers.get_supplier(1)
    rate_updated = suppliers.update_supplier_rate(1, SupplierRateUpdateInput(tarifa_por_kg=5.0), {"id": 1})

    assert fetched.id == rate_updated.id == 1
    monkeypatch.setattr(suppliers, "get_suppliers_repository", lambda: _SupplierRepository(RuntimeError("delete failed")))
    with pytest.raises(HTTPException, match="Error interno al eliminar") as failed:
        suppliers.delete_supplier(1, {"id": 1})
    assert failed.value.status_code == 500