"""Gestión de tokens de restablecimiento de contraseña."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from tinydb import Query, TinyDB

from auth_db import _resolve_auth_db_path


class TokenExpiredError(Exception):
    """El token de restablecimiento ha expirado."""


class TokenUsedError(Exception):
    """El token de restablecimiento ya fue utilizado."""


class TokenNotFoundError(Exception):
    """El token de restablecimiento no existe."""


def _hash_token(token: str) -> str:
    """Genera un hash SHA-256 del token para almacenarlo de forma segura."""
    return hashlib.sha256(token.encode()).hexdigest()


class ResetTokenRepository:
    """Repositorio para tokens de restablecimiento en TinyDB."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = TinyDB(db_path)
        self._table = self._db.table("reset_tokens")

    def create(self, user_id: int, expires_minutes: int = 30) -> str:
        """
        Genera un nuevo token de restablecimiento para el usuario.

        Retorna el token en texto plano (para incluir en el email).
        Almacena solo el hash SHA-256 en la base de datos.
        """
        token = secrets.token_urlsafe(32)
        token_hash = _hash_token(token)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=expires_minutes)

        self._table.insert({
            "token_hash": token_hash,
            "user_id": user_id,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "used": False,
        })

        return token

    def validate(self, token: str) -> int:
        """
        Valida un token de restablecimiento.

        Verifica que:
        1. El token exista en la base de datos
        2. No haya sido utilizado
        3. No haya expirado

        Si es válido, marca el token como usado y retorna el user_id.
        Lanza TokenNotFoundError, TokenUsedError o TokenExpiredError
        si el token no es válido.
        """
        token_hash = _hash_token(token)
        Record = Query()
        doc = self._table.get(Record.token_hash == token_hash)

        if doc is None:
            raise TokenNotFoundError("El token de restablecimiento no es válido.")

        if doc["used"]:
            raise TokenUsedError("El token de restablecimiento ya fue utilizado.")

        now = datetime.now(timezone.utc)
        expires_at = datetime.fromisoformat(doc["expires_at"])

        if now > expires_at:
            raise TokenExpiredError("El token de restablecimiento ha expirado.")

        # Marcar como usado
        self._table.update({"used": True}, doc_ids=[doc.doc_id])

        return doc["user_id"]

    def invalidate_all_for_user(self, user_id: int) -> None:
        """Invalida todos los tokens activos de un usuario (opcional, para limpieza)."""
        Record = Query()
        self._table.update(
            {"used": True},
            (Record.user_id == user_id) & (Record.used == False),
        )


def _resolve_reset_tokens_db_path() -> Path:
    """Resuelve la ruta de la base de datos de tokens de reset."""
    import os
    env_path = os.getenv("TRACKFLOW_AUTH_DB_PATH")
    if env_path:
        return Path(env_path)
    from auth_db import DEFAULT_AUTH_DB_PATH
    return DEFAULT_AUTH_DB_PATH


@lru_cache
def get_reset_token_repository() -> ResetTokenRepository:
    """Retorna una instancia cacheada del repositorio de tokens."""
    return ResetTokenRepository(_resolve_reset_tokens_db_path())
