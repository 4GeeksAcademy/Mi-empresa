from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from tinydb import Query, TinyDB

from auth_models import (
    ProfilePersistence,
    ProfileResponse,
    UserPersistence,
    UserResponse,
)

DEFAULT_AUTH_DB_PATH = Path(__file__).resolve().parent / "data" / "auth.json"


class UserRepository:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = TinyDB(db_path)
        self._table = self._db.table("users")

    def _to_response(self, doc: Any) -> UserResponse:
        return UserResponse(
            id=doc.doc_id,
            email=doc["email"],
            role=doc["role"],
            is_active=doc["is_active"],
            created_at=doc["created_at"],
        )

    def create(self, payload: UserPersistence) -> UserResponse:
        doc_id = self._table.insert(payload.model_dump())
        created = self._table.get(doc_id=doc_id)
        if created is None:
            raise RuntimeError("No se pudo recuperar el usuario recien insertado.")
        return self._to_response(created)

    def get(self, user_id: int) -> UserResponse | None:
        doc = self._table.get(doc_id=user_id)
        if doc is None:
            return None
        return self._to_response(doc)

    def get_by_email(self, email: str) -> UserResponse | None:
        user = Query()
        doc = self._table.get(user.email == email.strip().lower())
        if doc is None:
            return None
        return self._to_response(doc)

    def get_raw(self, user_id: int) -> dict[str, Any] | None:
        """Devuelve el documento completo (incluyendo hashed_password)."""
        doc = self._table.get(doc_id=user_id)
        if doc is None:
            return None
        data = dict(doc)
        data["id"] = doc.doc_id
        return data

    def get_raw_by_email(self, email: str) -> dict[str, Any] | None:
        """Devuelve el documento completo por email."""
        user = Query()
        doc = self._table.get(user.email == email.strip().lower())
        if doc is None:
            return None
        data = dict(doc)
        data["id"] = doc.doc_id
        return data

    def list(self) -> list[UserResponse]:
        return [self._to_response(doc) for doc in self._table.all()]

    def update(self, user_id: int, updates: dict[str, Any]) -> UserResponse | None:
        existing = self._table.get(doc_id=user_id)
        if existing is None:
            return None
        self._table.update(updates, doc_ids=[user_id])
        updated = self._table.get(doc_id=user_id)
        if updated is None:
            return None
        return self._to_response(updated)

    def delete(self, user_id: int) -> bool:
        try:
            removed = self._table.remove(doc_ids=[user_id])
            return bool(removed)
        except KeyError:
            return False


class ProfileRepository:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = TinyDB(db_path)
        self._table = self._db.table("profiles")

    def _to_response(self, doc: Any) -> ProfileResponse:
        return ProfileResponse(
            id=doc.doc_id,
            user_id=doc["user_id"],
            name=doc.get("name"),
            phone=doc.get("phone"),
            address=doc.get("address"),
        )

    def create(self, payload: ProfilePersistence) -> ProfileResponse:
        doc_id = self._table.insert(payload.model_dump())
        created = self._table.get(doc_id=doc_id)
        if created is None:
            raise RuntimeError("No se pudo recuperar el perfil recien insertado.")
        return self._to_response(created)

    def get_by_user_id(self, user_id: int) -> ProfileResponse | None:
        profile = Query()
        doc = self._table.get(profile.user_id == user_id)
        if doc is None:
            return None
        return self._to_response(doc)

    def update_by_user_id(self, user_id: int, updates: dict[str, Any]) -> ProfileResponse | None:
        profile = Query()
        existing = self._table.get(profile.user_id == user_id)
        if existing is None:
            return None
        self._table.update(updates, profile.user_id == user_id)
        updated = self._table.get(profile.user_id == user_id)
        if updated is None:
            return None
        return self._to_response(updated)

    def delete_by_user_id(self, user_id: int) -> bool:
        profile = Query()
        try:
            removed = self._table.remove(profile.user_id == user_id)
            return bool(removed)
        except KeyError:
            return False


def _resolve_auth_db_path() -> Path:
    import os

    env_path = os.getenv("TRACKFLOW_AUTH_DB_PATH")
    if env_path:
        return Path(env_path)
    return DEFAULT_AUTH_DB_PATH


@lru_cache
def get_user_repository() -> UserRepository:
    return UserRepository(_resolve_auth_db_path())


@lru_cache
def get_profile_repository() -> ProfileRepository:
    return ProfileRepository(_resolve_auth_db_path())