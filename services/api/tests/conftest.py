from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(autouse=True)
def isolated_auth_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Aisla los repositorios de autenticacion en una TinyDB por prueba."""
    import auth
    from auth_db import get_profile_repository, get_user_repository
    from reset_tokens import get_reset_token_repository

    monkeypatch.setenv("TRACKFLOW_AUTH_DB_PATH", str(tmp_path / "auth.json"))
    monkeypatch.setattr(auth, "SECRET_KEY", "test-secret-key-for-auth-088")
    get_user_repository.cache_clear()
    get_profile_repository.cache_clear()
    get_reset_token_repository.cache_clear()

    yield

    get_user_repository.cache_clear()
    get_profile_repository.cache_clear()
    get_reset_token_repository.cache_clear()
