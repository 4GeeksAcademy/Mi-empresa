from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from auth import get_current_user
from auth_db import get_profile_repository
from auth_models import ProfileResponse, ProfileUpdateInput

router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.get("/me", response_model=ProfileResponse)
def get_my_profile(
    current_user: dict = Depends(get_current_user),
) -> ProfileResponse:
    """Devuelve el perfil del usuario autenticado (protegida)."""
    repo = get_profile_repository()
    profile = repo.get_by_user_id(current_user["id"])
    if profile is None:
        raise HTTPException(status_code=404, detail="Perfil no encontrado.")
    return profile


@router.put("/me", response_model=ProfileResponse)
def update_my_profile(
    payload: ProfileUpdateInput,
    current_user: dict = Depends(get_current_user),
) -> ProfileResponse:
    """
    Actualiza name, phone y address del perfil del usuario autenticado.
    Solo el dueno del perfil puede modificarlo (protegida).
    """
    repo = get_profile_repository()

    existing = repo.get_by_user_id(current_user["id"])
    if existing is None:
        raise HTTPException(status_code=404, detail="Perfil no encontrado.")

    updates: dict = {}
    if payload.name is not None:
        updates["name"] = payload.name
    if payload.phone is not None:
        updates["phone"] = payload.phone
    if payload.address is not None:
        updates["address"] = payload.address

    if not updates:
        return existing

    updated = repo.update_by_user_id(current_user["id"], updates)
    if updated is None:
        raise HTTPException(status_code=404, detail="Perfil no encontrado.")
    return updated