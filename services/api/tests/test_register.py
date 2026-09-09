"""Pruebas unitarias de registro y administracion de usuarios."""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from auth_db import get_profile_repository, get_user_repository
from auth_models import ProfilePersistence, UserCreateInput, UserPersistence, UserRole, utc_now_iso
from routes import users


def _persist_user(email: str, *, role: str = "user") -> int:
    created = get_user_repository().create(
        UserPersistence(
            email=email,
            hashed_password="hashed-password",
            role=role,
            is_active=True,
            created_at=utc_now_iso(),
        )
    )
    return created.id


def test_create_user_hashes_password_and_creates_optional_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(users, "hash_password", lambda password: f"hashed:{password}")

    created = users.create_user(
        UserCreateInput(
            email="  Register@TrackFlow.com ",
            password="secure123",
            name="Ana",
            phone="+34123456789",
        )
    )

    raw_user = get_user_repository().get_raw(created.id)
    profile = get_profile_repository().get_by_user_id(created.id)
    assert created.email == "register@trackflow.com"
    assert raw_user is not None
    assert raw_user["hashed_password"] == "hashed:secure123"
    assert profile is not None
    assert profile.name == "Ana"
    assert profile.phone == "+34123456789"


def test_create_user_rejects_duplicate_email(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(users, "hash_password", lambda password: password)
    users.create_user(UserCreateInput(email="duplicate@trackflow.com", password="secure123"))

    with pytest.raises(HTTPException, match="Ya existe") as raised:
        users.create_user(UserCreateInput(email="DUPLICATE@trackflow.com", password="secure456"))

    assert raised.value.status_code == 409


def test_user_input_normalizes_email_and_rejects_invalid_credentials() -> None:
    payload = UserCreateInput(email="  User@TrackFlow.com ", password="secure123")

    assert payload.email == "user@trackflow.com"
    with pytest.raises(ValidationError, match="email debe contener"):
        UserCreateInput(email="invalid-email", password="secure123")
    with pytest.raises(ValidationError):
        UserCreateInput(email="user@trackflow.com", password="12345")


def test_admin_can_update_user_but_regular_user_cannot_change_role() -> None:
    target_id = _persist_user("target@trackflow.com")
    admin = {"id": 99, "role": UserRole.ADMIN.value}

    updated = users.update_user(
        target_id,
        users.UserUpdateInput(email="new-target@trackflow.com"),
        admin,
    )

    assert updated.email == "new-target@trackflow.com"
    with pytest.raises(HTTPException, match="Solo un admin") as raised:
        users.update_user(
            target_id,
            users.UserUpdateInput(role=UserRole.ADMIN),
            {"id": target_id, "role": UserRole.USER.value},
        )
    assert raised.value.status_code == 403


def test_list_and_get_user_return_existing_users_and_reject_missing_user() -> None:
    user_id = _persist_user("listed@trackflow.com")
    current_user = {"id": user_id, "role": UserRole.USER.value}

    listed = users.list_users(current_user)
    fetched = users.get_user(user_id, current_user)

    assert [user.id for user in listed] == [user_id]
    assert fetched.email == "listed@trackflow.com"
    with pytest.raises(HTTPException, match="Usuario no encontrado"):
        users.get_user(999, current_user)


def test_delete_user_removes_linked_profile_and_rejects_missing_user() -> None:
    user_id = _persist_user("remove@trackflow.com")
    get_profile_repository().create(ProfilePersistence(user_id=user_id, name="To remove"))
    admin = {"id": 99, "role": UserRole.ADMIN.value}

    users.delete_user(user_id, admin)

    assert get_user_repository().get(user_id) is None
    assert get_profile_repository().get_by_user_id(user_id) is None
    with pytest.raises(HTTPException, match="no encontrado") as raised:
        users.delete_user(user_id, admin)
    assert raised.value.status_code == 404