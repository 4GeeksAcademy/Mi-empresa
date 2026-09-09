"""Pruebas unitarias de recuperacion y cambio de contrasena."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from auth_db import get_user_repository
from auth_models import ChangePasswordInput, ForgotPasswordInput, ResetPasswordInput, UserPersistence, utc_now_iso
from reset_tokens import TokenExpiredError, TokenNotFoundError, TokenUsedError, get_reset_token_repository
from routes import auth as auth_routes


def _create_user(email: str = "reset@trackflow.com", *, active: bool = True) -> int:
    return get_user_repository().create(UserPersistence(email=email, hashed_password="old-hash", role="user", is_active=active, created_at=utc_now_iso())).id


class _TokenRepository:
    def __init__(self, result: int | Exception) -> None:
        self.result = result

    def validate(self, token: str) -> int:
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_forgot_password_sends_token_only_for_active_user(monkeypatch: pytest.MonkeyPatch) -> None:
    created_user_id = _create_user()
    calls: list[tuple[str, str]] = []

    class TokenCreator:
        def create(self, user_id: int, expires_minutes: int) -> str:
            assert (user_id, expires_minutes) == (created_user_id, 30)
            return "reset-token"

    monkeypatch.setattr(auth_routes, "get_reset_token_repository", lambda: TokenCreator())
    monkeypatch.setattr(auth_routes, "send_password_reset_email", lambda email, token: calls.append((email, token)))

    response = auth_routes.forgot_password(ForgotPasswordInput(email="RESET@trackflow.com"))

    assert response.message == auth_routes.FORGOT_PASSWORD_MESSAGE
    assert calls == [("reset@trackflow.com", "reset-token")]


def test_forgot_password_hides_nonexistent_and_inactive_accounts(monkeypatch: pytest.MonkeyPatch) -> None:
    _create_user("inactive@trackflow.com", active=False)
    monkeypatch.setattr(auth_routes, "send_password_reset_email", lambda email, token: pytest.fail("No se debe enviar correo"))

    missing = auth_routes.forgot_password(ForgotPasswordInput(email="missing@trackflow.com"))
    inactive = auth_routes.forgot_password(ForgotPasswordInput(email="inactive@trackflow.com"))

    assert missing.message == inactive.message == auth_routes.FORGOT_PASSWORD_MESSAGE


def test_reset_password_updates_password_for_valid_token(monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = _create_user()
    monkeypatch.setattr(auth_routes, "get_reset_token_repository", lambda: _TokenRepository(user_id))
    monkeypatch.setattr(auth_routes, "hash_password", lambda password: f"hashed:{password}")

    response = auth_routes.reset_password(ResetPasswordInput(token="valid-token", new_password="new-password"))

    assert response.message == "Contraseña actualizada correctamente."
    assert get_user_repository().get_raw(user_id)["hashed_password"] == "hashed:new-password"


@pytest.mark.parametrize("error", [TokenNotFoundError("no existe"), TokenExpiredError("expirado"), TokenUsedError("usado")])
def test_reset_password_rejects_invalid_token_states(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    monkeypatch.setattr(auth_routes, "get_reset_token_repository", lambda: _TokenRepository(error))

    with pytest.raises(HTTPException, match=str(error)):
        auth_routes.reset_password(ResetPasswordInput(token="invalid-token", new_password="new-pass"))


def test_reset_password_rejects_deleted_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_routes, "get_reset_token_repository", lambda: _TokenRepository(999))
    monkeypatch.setattr(auth_routes, "hash_password", lambda password: password)

    with pytest.raises(HTTPException, match="usuario no existe"):
        auth_routes.reset_password(ResetPasswordInput(token="valid-token", new_password="new-pass"))


def test_reset_token_repository_rejects_expired_and_reused_tokens() -> None:
    token_repository = get_reset_token_repository()
    user_id = _create_user()
    expired_token = token_repository.create(user_id, expires_minutes=-1)
    reusable_token = token_repository.create(user_id)

    with pytest.raises(TokenExpiredError):
        token_repository.validate(expired_token)
    assert token_repository.validate(reusable_token) == user_id
    with pytest.raises(TokenUsedError):
        token_repository.validate(reusable_token)


def test_change_password_requires_current_password_and_updates_it(monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = _create_user()
    monkeypatch.setattr(auth_routes, "verify_password", lambda plain, hashed: plain == "old-password")
    monkeypatch.setattr(auth_routes, "hash_password", lambda password: f"hashed:{password}")

    response = auth_routes.change_password(ChangePasswordInput(current_password="old-password", new_password="new-password"), {"id": user_id})

    assert response.message == "Contraseña cambiada correctamente."
    assert get_user_repository().get_raw(user_id)["hashed_password"] == "hashed:new-password"
    with pytest.raises(HTTPException, match="incorrecta"):
        auth_routes.change_password(ChangePasswordInput(current_password="wrong-password", new_password="another-password"), {"id": user_id})


def test_change_password_rejects_missing_current_user() -> None:
    with pytest.raises(HTTPException, match="Usuario no encontrado"):
        auth_routes.change_password(ChangePasswordInput(current_password="old-password", new_password="new-password"), {"id": 999})