from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from auth import get_current_user, hash_password
from auth_db import get_user_repository, get_profile_repository
from auth_models import (
    UserCreateInput,
    UserResponse,
    UserUpdateInput,
    UserPersistence,
    UserRole,
    ProfilePersistence,
    ProfileCreateInput,
    utc_now_iso,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreateInput) -> UserResponse:
    """Registrar un nuevo usuario (público)."""
    repo = get_user_repository()

    existing = repo.get_by_email(payload.email)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe un usuario con ese email.",
        )

    hashed = hash_password(payload.password)
    user_persistence = UserPersistence(
        email=payload.email.strip().lower(),
        hashed_password=hashed,
        role=payload.role.value,
        is_active=True,
        created_at=utc_now_iso(),
    )

    created = repo.create(user_persistence)

    # Crear perfil vinculado si se proporcionaron datos opcionales
    if payload.name or payload.phone or payload.address:
        profile_repo = get_profile_repository()
        profile_payload = ProfilePersistence(
            user_id=created.id,
            name=payload.name,
            phone=payload.phone,
            address=payload.address,
        )
        profile_repo.create(profile_payload)

    return created


@router.get("", response_model=list[UserResponse])
def list_users(
    current_user: dict = Depends(get_current_user),
) -> list[UserResponse]:
    """Listar todos los usuarios (protegida)."""
    repo = get_user_repository()
    return repo.list()


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: int,
    current_user: dict = Depends(get_current_user),
) -> UserResponse:
    """Obtener un usuario por ID (protegida)."""
    repo = get_user_repository()
    user = repo.get(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    return user


@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    payload: UserUpdateInput,
    current_user: dict = Depends(get_current_user),
) -> UserResponse:
    """
    Actualizar campos de credenciales (protegida).
    Solo el propio usuario o un admin pueden actualizar.
    Solo un admin puede cambiar el role.
    """
    repo = get_user_repository()

    existing = repo.get(user_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    # Verificar permisos: solo el propio usuario o un admin
    is_self = current_user["id"] == user_id
    is_admin = current_user["role"] == UserRole.ADMIN.value

    if not is_self and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para actualizar este usuario.",
        )

    updates: dict = {}

    if payload.email is not None:
        if not is_self and not is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo el propio usuario o un admin puede cambiar el email.",
            )
        # Verificar que el email no esté en uso por otro usuario
        existing_email = repo.get_by_email(payload.email)
        if existing_email is not None and existing_email.id != user_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="El email ya esta en uso por otro usuario.",
            )
        updates["email"] = payload.email.strip().lower()

    if payload.role is not None:
        if not is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo un admin puede cambiar el rol.",
            )
        updates["role"] = payload.role.value

    if payload.is_active is not None:
        if not is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo un admin puede cambiar el estado activo.",
            )
        updates["is_active"] = payload.is_active

    if not updates:
        return existing

    updated = repo.update(user_id, updates)
    if updated is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    return updated


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    current_user: dict = Depends(get_current_user),
) -> None:
    """Eliminar un usuario y su perfil vinculado (protegida)."""
    repo = get_user_repository()
    profile_repo = get_profile_repository()

    existing = repo.get(user_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    # Eliminar perfil vinculado
    profile_repo.delete_by_user_id(user_id)

    # Eliminar usuario
    deleted = repo.delete(user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")