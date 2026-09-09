"""Pruebas unitarias de perfiles autenticados."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from auth_db import get_profile_repository
from auth_models import ProfilePersistence, ProfileUpdateInput
from routes import auth as auth_routes
from routes import profiles


def test_get_my_profile_returns_existing_profile() -> None:
    profile = get_profile_repository().create(ProfilePersistence(user_id=11, name="Ana"))
    assert profiles.get_my_profile({"id": 11}) == profile


def test_get_my_profile_rejects_missing_profile() -> None:
    with pytest.raises(HTTPException, match="Perfil no encontrado"):
        profiles.get_my_profile({"id": 11})


def test_auth_me_includes_profile_when_present_or_none_when_missing() -> None:
    current_user = {"id": 11, "email": "profile@trackflow.com", "role": "user"}

    without_profile = auth_routes.get_me(current_user)
    get_profile_repository().create(ProfilePersistence(user_id=11, name="Ana"))
    with_profile = auth_routes.get_me(current_user)

    assert without_profile.profile is None
    assert with_profile.profile is not None
    assert with_profile.profile.name == "Ana"


def test_update_my_profile_changes_provided_fields_and_preserves_empty_update() -> None:
    get_profile_repository().create(ProfilePersistence(user_id=11, name="Ana", phone="111", address="Old street"))

    updated = profiles.update_my_profile(ProfileUpdateInput(phone="222"), {"id": 11})
    unchanged = profiles.update_my_profile(ProfileUpdateInput(), {"id": 11})

    assert (updated.name, updated.phone, updated.address) == ("Ana", "222", "Old street")
    assert unchanged == updated


def test_update_my_profile_rejects_missing_profile() -> None:
    with pytest.raises(HTTPException, match="Perfil no encontrado"):
        profiles.update_my_profile(ProfileUpdateInput(name="Ana"), {"id": 11})