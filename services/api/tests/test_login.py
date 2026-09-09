"""Pruebas unitarias de inicio de sesion."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from auth_db import get_user_repository
from auth_models import LoginInput, UserPersistence, utc_now_iso
from routes import auth as auth_routes


def _create_user(*, active: bool = True) -> int:
    return get_user_repository().create(UserPersistence(email="login@trackflow.com", hashed_password="stored-hash", role="user", is_active=active, created_at=utc_now_iso())).id


def test_login_returns_token_for_valid_active_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = _create_user()
    monkeypatch.setattr(auth_routes, "verify_password", lambda plain, hashed: plain == "correct-password")
    monkeypatch.setattr(auth_routes, "create_access_token", lambda data: f"token-for-{data['sub']}")

    response = auth_routes.login(LoginInput(email="LOGIN@trackflow.com", password="correct-password"))

    assert response.access_token == f"token-for-{user_id}"
    assert response.token_type == "bearer"


@pytest.mark.parametrize("email,password,active", [("missing@trackflow.com", "correct-password", True), ("login@trackflow.com", "wrong-password", True), ("login@trackflow.com", "correct-password", False)])
def test_login_rejects_missing_invalid_or_inactive_credentials(monkeypatch: pytest.MonkeyPatch, email: str, password: str, active: bool) -> None:
    _create_user(active=active)
    monkeypatch.setattr(auth_routes, "verify_password", lambda plain, hashed: plain == "correct-password")

    with pytest.raises(HTTPException):
        auth_routes.login(LoginInput(email=email, password=password))