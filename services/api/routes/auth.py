from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from auth import create_access_token, get_current_user, hash_password, verify_password
from auth_db import get_user_repository, get_profile_repository
from auth_models import (
    AuthMeResponse,
    ChangePasswordInput,
    ForgotPasswordInput,
    LoginInput,
    MessageResponse,
    ResetPasswordInput,
    TokenResponse,
)
from email_service import send_password_reset_email
from reset_tokens import (
    TokenExpiredError,
    TokenNotFoundError,
    TokenUsedError,
    get_reset_token_repository,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginInput) -> TokenResponse:
    repo = get_user_repository()
    user_doc = repo.get_raw_by_email(payload.email)
    if user_doc is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contrasena incorrectos.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not verify_password(payload.password, user_doc["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contrasena incorrectos.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user_doc.get("is_active", False):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario inactivo.",
        )

    access_token = create_access_token(data={"sub": str(user_doc["id"])})
    return TokenResponse(access_token=access_token)


@router.get("/me", response_model=AuthMeResponse)
def get_me(current_user: dict = Depends(get_current_user)) -> AuthMeResponse:
    profile_repo = get_profile_repository()
    profile = profile_repo.get_by_user_id(current_user["id"])
    return AuthMeResponse(
        id=current_user["id"],
        email=current_user["email"],
        role=current_user["role"],
        profile=profile,
    )


# ── Recuperación y cambio de contraseña ──────────────────────────────

FORGOT_PASSWORD_MESSAGE = (
    "Si esa dirección está registrada, recibirás un enlace de restablecimiento en breve."
)


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(payload: ForgotPasswordInput) -> MessageResponse:
    """
    Solicita un restablecimiento de contraseña.

    SIEMPRE devuelve 200 con el mismo mensaje, independientemente de si
    el email existe o no, para evitar enumeración de usuarios.
    """
    repo = get_user_repository()
    user_doc = repo.get_raw_by_email(payload.email)

    if user_doc is not None and user_doc.get("is_active", False):
        token_repo = get_reset_token_repository()
        token = token_repo.create(user_id=user_doc["id"], expires_minutes=30)
        send_password_reset_email(email=payload.email, token=token)

    return MessageResponse(message=FORGOT_PASSWORD_MESSAGE)


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(payload: ResetPasswordInput) -> MessageResponse:
    """
    Restablece la contraseña usando un token de restablecimiento.

    Valida el token (expiración y uso), hashea la nueva contraseña
    y actualiza el registro del usuario.
    """
    token_repo = get_reset_token_repository()
    try:
        user_id = token_repo.validate(payload.token)
    except TokenNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except TokenExpiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except TokenUsedError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    # Actualizar la contraseña del usuario
    user_repo = get_user_repository()
    new_hashed = hash_password(payload.new_password)
    updated = user_repo.update(user_id, {"hashed_password": new_hashed})

    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se pudo actualizar la contraseña. El usuario no existe.",
        )

    return MessageResponse(message="Contraseña actualizada correctamente.")


@router.post("/change-password", response_model=MessageResponse)
def change_password(
    payload: ChangePasswordInput,
    current_user: dict = Depends(get_current_user),
) -> MessageResponse:
    """
    Cambia la contraseña de un usuario autenticado.

    Requiere la contraseña actual para verificar identidad antes de actualizar.
    """
    user_repo = get_user_repository()
    user_doc = user_repo.get_raw(current_user["id"])

    if user_doc is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado.",
        )

    if not verify_password(payload.current_password, user_doc["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La contraseña actual es incorrecta.",
        )

    new_hashed = hash_password(payload.new_password)
    user_repo.update(current_user["id"], {"hashed_password": new_hashed})

    return MessageResponse(message="Contraseña cambiada correctamente.")