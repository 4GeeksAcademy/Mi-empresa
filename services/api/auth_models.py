from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class UserRole(str, Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    USER = "user"


class UserCreateInput(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=6, max_length=255)
    role: UserRole = UserRole.USER
    # Opcionales para crear el perfil junto con el usuario
    name: str | None = None
    phone: str | None = None
    address: str | None = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized:
            raise ValueError("El email debe contener un @.")
        return normalized


class UserUpdateInput(BaseModel):
    email: str | None = Field(default=None, min_length=5, max_length=255)
    role: UserRole | None = None
    is_active: bool | None = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if "@" not in normalized:
            raise ValueError("El email debe contener un @.")
        return normalized


class UserResponse(BaseModel):
    id: int
    email: str
    role: UserRole
    is_active: bool
    created_at: str

    model_config = ConfigDict(from_attributes=True)


class UserPersistence(BaseModel):
    email: str
    hashed_password: str
    role: str
    is_active: bool
    created_at: str


class ProfileCreateInput(BaseModel):
    user_id: int
    name: str | None = None
    phone: str | None = None
    address: str | None = None


class ProfileUpdateInput(BaseModel):
    name: str | None = None
    phone: str | None = None
    address: str | None = None


class ProfileResponse(BaseModel):
    id: int
    user_id: int
    name: str | None = None
    phone: str | None = None
    address: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ProfilePersistence(BaseModel):
    user_id: int
    name: str | None = None
    phone: str | None = None
    address: str | None = None


class LoginInput(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AuthMeResponse(BaseModel):
    id: int
    email: str
    role: UserRole
    profile: ProfileResponse | None = None


# ── Modelos para recuperación y cambio de contraseña ──────────────────


class ForgotPasswordInput(BaseModel):
    email: str = Field(min_length=5, max_length=255)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized:
            raise ValueError("El email debe contener un @.")
        return normalized


class ResetPasswordInput(BaseModel):
    token: str = Field(min_length=1, max_length=255)
    new_password: str = Field(min_length=6, max_length=255)


class ChangePasswordInput(BaseModel):
    current_password: str = Field(min_length=1, max_length=255)
    new_password: str = Field(min_length=6, max_length=255)


class MessageResponse(BaseModel):
    message: str


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()