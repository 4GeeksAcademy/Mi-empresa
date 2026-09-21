"""Small in-process TTL cache used for read-heavy API responses.

The cache is intentionally process-local. It is appropriate for the current
single-process deployment; a shared Redis cache should replace it when the API
runs across multiple replicas.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Lock
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass
class _Entry(Generic[T]):
    value: T
    expires_at: float


class TTLCache(Generic[T]):
    def __init__(self) -> None:
        self._entries: dict[str, _Entry[T]] = {}
        self._lock = Lock()

    def get(self, key: str) -> T | None:
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expires_at <= now:
                del self._entries[key]
                return None
            return entry.value

    def set(self, key: str, value: T, ttl_seconds: float) -> None:
        with self._lock:
            self._entries[key] = _Entry(value=value, expires_at=time.monotonic() + ttl_seconds)

    def invalidate(self, prefix: str | None = None) -> None:
        with self._lock:
            if prefix is None:
                self._entries.clear()
            else:
                for key in [key for key in self._entries if key.startswith(prefix)]:
                    del self._entries[key]

    def clear(self) -> None:
        self.invalidate()


# Read endpoints use separate caches so invalidating one domain cannot affect another.
suppliers_cache: TTLCache[object] = TTLCache()
incidents_cache: TTLCache[object] = TTLCache()
