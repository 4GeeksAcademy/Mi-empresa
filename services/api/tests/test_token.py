"""Pruebas unitarias de autorizacion JWT."""
from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest
from fastapi import HTTPException
from jose import jwt

import auth
from auth_db import get_user_repository
from auth_models import UserPersistence, utc_now_iso


def _create_user(*, active: bool = True) -> int:
    return get_user_repository().create(UserPersistence(email="token@trackflow.com", hashed_password="stored-hash", role="user", is_active=active, created_at=utc_now_iso())).id


def test_current_user_accepts_valid_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth, "SECRET_KEY", "unit-test-secret")
    user_id = _create_user()

    current_user = asyncio.run(auth.get_current_user(auth.create_access_token({"sub": str(user_id)})))

    assert current_user["id"] == user_id
    assert current_user["email"] == "token@trackflow.com"


@pytest.mark.parametrize("token", ["malformed-token", None])
def test_current_user_rejects_malformed_or_subjectless_token(monkeypatch: pytest.MonkeyPatch, token: str | None) -> None:
    monkeypatch.setattr(auth, "SECRET_KEY", "unit-test-secret")
    actual_token = token or jwt.encode({"scope": "user"}, "unit-test-secret", algorithm=auth.ALGORITHM)

    with pytest.raises(HTTPException, match="validar"):
        asyncio.run(auth.get_current_user(actual_token))


def test_current_user_rejects_expired_or_inactive_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth, "SECRET_KEY", "unit-test-secret")
    user_id = _create_user(active=False)
    expired_token = auth.create_access_token({"sub": str(user_id)}, timedelta(seconds=-1))
    inactive_token = auth.create_access_token({"sub": str(user_id)})

    with pytest.raises(HTTPException, match="validar"):
        asyncio.run(auth.get_current_user(expired_token))
    with pytest.raises(HTTPException, match="validar"):
        asyncio.run(auth.get_current_user(inactive_token))


def test_current_admin_accepts_admin_and_rejects_regular_user() -> None:
    admin = {"id": 1, "role": "admin"}
    assert asyncio.run(auth.get_current_admin(admin)) == admin
    with pytest.raises(HTTPException, match="rol admin"):
        asyncio.run(auth.get_current_admin({"id": 2, "role": "user"}))