from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from auth import get_current_user
from database import get_suppliers_repository
from models import (
    SupplierCategory,
    SupplierCountry,
    SupplierCreateInput,
    SupplierFilters,
    SupplierRateUpdateInput,
    SupplierResponse,
    SupplierStatusUpdateInput,
)

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


@router.post("", response_model=SupplierResponse, status_code=status.HTTP_201_CREATED)
def create_supplier(
    payload: SupplierCreateInput,
    current_user: dict = Depends(get_current_user),
) -> SupplierResponse:
    repo = get_suppliers_repository()
    return repo.create(payload)


@router.get("", response_model=list[SupplierResponse])
def list_suppliers(
    pais: SupplierCountry | None = Query(default=None),
    categoria: SupplierCategory | None = Query(default=None),
    country: SupplierCountry | None = Query(default=None),
    category: SupplierCategory | None = Query(default=None),
) -> list[SupplierResponse]:
    filters = SupplierFilters(
        pais=pais or country,
        categoria=categoria or category,
    )
    repo = get_suppliers_repository()
    return repo.list(filters)


@router.get("/{supplier_id}", response_model=SupplierResponse)
def get_supplier(supplier_id: int) -> SupplierResponse:
    repo = get_suppliers_repository()
    supplier = repo.get(supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado.")
    return supplier


@router.patch("/{supplier_id}/rate", response_model=SupplierResponse)
def update_supplier_rate(
    supplier_id: int,
    payload: SupplierRateUpdateInput,
    current_user: dict = Depends(get_current_user),
) -> SupplierResponse:
    repo = get_suppliers_repository()
    updated = repo.update_rate(supplier_id, payload.tarifa_por_kg)
    if updated is None:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado.")
    return updated


@router.patch("/{supplier_id}/status", response_model=SupplierResponse)
def update_supplier_status(
    supplier_id: int,
    payload: SupplierStatusUpdateInput,
    current_user: dict = Depends(get_current_user),
) -> SupplierResponse:
    repo = get_suppliers_repository()
    updated = repo.update_status(supplier_id, payload.status)
    if updated is None:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado.")
    return updated


@router.delete("/{supplier_id}")
def delete_supplier(
    supplier_id: int,
    current_user: dict = Depends(get_current_user),
) -> dict[str, str]:
    repo = get_suppliers_repository()
    deleted = repo.delete(supplier_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado.")
    return {"detail": "Proveedor eliminado."}
