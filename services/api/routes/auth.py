from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from auth import create_access_token, get_current_user, verify_password
from auth_db import get_user_repository, get_profile_repository
from auth_models import AuthMeResponse, LoginInput, TokenResponse

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