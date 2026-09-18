from __future__ import annotations

import time

from cache import TTLCache


def test_ttl_cache_expires_values() -> None:
    cache: TTLCache[str] = TTLCache()
    cache.set("key", "value", ttl_seconds=0.01)
    assert cache.get("key") == "value"
    time.sleep(0.02)
    assert cache.get("key") is None


def test_ttl_cache_invalidates_by_prefix() -> None:
    cache: TTLCache[str] = TTLCache()
    cache.set("suppliers:list:US:-", "us", ttl_seconds=60)
    cache.set("suppliers:list:ES:-", "es", ttl_seconds=60)
    cache.set("other", "kept", ttl_seconds=60)
    cache.invalidate("suppliers:list:")
    assert cache.get("suppliers:list:US:-") is None
    assert cache.get("other") == "kept"