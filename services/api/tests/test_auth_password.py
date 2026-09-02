"""Tests para recuperación y cambio de contraseña (AUTH-03)."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from auth import create_access_token, hash_password
from auth_db import get_user_repository, get_profile_repository
from auth_models import UserPersistence, utc_now_iso
from main import app
from reset_tokens import _hash_token, get_reset_token_repository

client = TestClient(app)

TEST_USER_EMAIL = "reset-test@trackflow.com"
TEST_USER_PASSWORD = "oldpass123"


def _create_test_user() -> int:
    """Crea un usuario de prueba y retorna su ID."""
    repo = get_user_repository()
    existing = repo.get_by_email(TEST_USER_EMAIL)
    if existing is not None:
        return existing.id

    user_persistence = UserPersistence(
        email=TEST_USER_EMAIL,
        hashed_password=hash_password(TEST_USER_PASSWORD),
        role="user",
        is_active=True,
        created_at=utc_now_iso(),
    )
    created = repo.create(user_persistence)
    return created.id


def _auth_header() -> dict[str, str]:
    """Crea header de autenticación para el usuario de prueba."""
    user_id = _create_test_user()
    token = create_access_token(data={"sub": str(user_id)})
    return {"Authorization": f"Bearer {token}"}


def setup_function() -> None:
    """Configura bases de datos temporales para cada test."""
    tmp_auth_db = Path("/tmp/trackflow-auth-password-test.json")
    if tmp_auth_db.exists():
        tmp_auth_db.unlink()
    os.environ["TRACKFLOW_AUTH_DB_PATH"] = str(tmp_auth_db)

    get_user_repository.cache_clear()
    get_profile_repository.cache_clear()
    get_reset_token_repository.cache_clear()


def teardown_function() -> None:
    """Limpia las bases de datos temporales después de cada test."""
    get_user_repository.cache_clear()
    get_profile_repository.cache_clear()
    get_reset_token_repository.cache_clear()
    os.environ.pop("TRACKFLOW_AUTH_DB_PATH", None)


# ── Tests de forgot-password ──────────────────────────────────────────


def test_forgot_password_existing_email_returns_200() -> None:
    """forgot-password con email existente devuelve 200 con mensaje genérico."""
    _create_test_user()
    response = client.post(
        "/auth/forgot-password",
        json={"email": TEST_USER_EMAIL},
    )
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "registrada" in data["message"].lower() or "enlace" in data["message"].lower()


def test_forgot_password_nonexistent_email_returns_200() -> None:
    """forgot-password con email inexistente devuelve 200 (no revela si existe)."""
    response = client.post(
        "/auth/forgot-password",
        json={"email": "noexiste@trackflow.com"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "message" in data


def test_forgot_password_same_message_both_cases() -> None:
    """forgot-password devuelve el mismo mensaje para emails existentes e inexistentes."""
    _create_test_user()

    resp_existing = client.post(
        "/auth/forgot-password",
        json={"email": TEST_USER_EMAIL},
    )
    resp_nonexistent = client.post(
        "/auth/forgot-password",
        json={"email": "otro@trackflow.com"},
    )
    assert resp_existing.json()["message"] == resp_nonexistent.json()["message"]


# ── Tests de reset-password ──────────────────────────────────────────


def test_reset_password_valid_token() -> None:
    """reset-password con token válido actualiza la contraseña."""
    user_id = _create_test_user()

    # Generar token manualmente
    token_repo = get_reset_token_repository()
    token = token_repo.create(user_id=user_id, expires_minutes=30)

    new_password = "newpass456"
    response = client.post(
        "/auth/reset-password",
        json={"token": token, "new_password": new_password},
    )
    assert response.status_code == 200

    # Verificar que puede hacer login con la nueva contraseña
    login_resp = client.post(
        "/auth/login",
        json={"email": TEST_USER_EMAIL, "password": new_password},
    )
    assert login_resp.status_code == 200
    assert "access_token" in login_resp.json()


def test_reset_password_used_token_returns_400() -> None:
    """reset-password con token ya usado devuelve 400."""
    user_id = _create_test_user()
    token_repo = get_reset_token_repository()
    token = token_repo.create(user_id=user_id, expires_minutes=30)

    # Primer uso - debe funcionar
    resp1 = client.post(
        "/auth/reset-password",
        json={"token": token, "new_password": "pass1111"},
    )
    assert resp1.status_code == 200

    # Segundo uso - debe fallar
    resp2 = client.post(
        "/auth/reset-password",
        json={"token": token, "new_password": "pass2222"},
    )
    assert resp2.status_code == 400


def test_reset_password_invalid_token_returns_400() -> None:
    """reset-password con token inexistente devuelve 400."""
    response = client.post(
        "/auth/reset-password",
        json={"token": "token-invalido-abc123", "new_password": "newpass123"},
    )
    assert response.status_code == 400


def test_reset_password_short_password_returns_422() -> None:
    """reset-password con contraseña menor a 6 caracteres devuelve 422."""
    user_id = _create_test_user()
    token_repo = get_reset_token_repository()
    token = token_repo.create(user_id=user_id, expires_minutes=30)

    response = client.post(
        "/auth/reset-password",
        json={"token": token, "new_password": "12345"},
    )
    assert response.status_code == 422


# ── Tests de change-password ─────────────────────────────────────────


def test_change_password_correct_current() -> None:
    """change-password con contraseña actual correcta devuelve 200."""
    headers = _auth_header()
    response = client.post(
        "/auth/change-password",
        json={
            "current_password": TEST_USER_PASSWORD,
            "new_password": "newpass789",
        },
        headers=headers,
    )
    assert response.status_code == 200
    assert "message" in response.json()

    # Verificar que puede hacer login con la nueva contraseña
    login_resp = client.post(
        "/auth/login",
        json={"email": TEST_USER_EMAIL, "password": "newpass789"},
    )
    assert login_resp.status_code == 200


def test_change_password_incorrect_current_returns_400() -> None:
    """change-password con contraseña actual incorrecta devuelve 400."""
    headers = _auth_header()
    response = client.post(
        "/auth/change-password",
        json={
            "current_password": "wrongpassword",
            "new_password": "newpass789",
        },
        headers=headers,
    )
    assert response.status_code == 400


def test_change_password_no_auth_returns_401() -> None:
    """change-password sin token de autenticación devuelve 401."""
    response = client.post(
        "/auth/change-password",
        json={
            "current_password": TEST_USER_PASSWORD,
            "new_password": "newpass789",
        },
    )
    assert response.status_code == 401


def test_change_password_short_new_password_returns_422() -> None:
    """change-password con nueva contraseña menor a 6 caracteres devuelve 422."""
    headers = _auth_header()
    response = client.post(
        "/auth/change-password",
        json={
            "current_password": TEST_USER_PASSWORD,
            "new_password": "12345",
        },
        headers=headers,
    )
    assert response.status_code == 422
