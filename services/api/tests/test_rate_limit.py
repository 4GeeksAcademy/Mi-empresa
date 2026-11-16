from rate_limit import InMemoryRateLimiter


def test_limiter_allows_limit_then_returns_retry_after(monkeypatch):
    ticks = iter([100.0, 101.0, 102.0])
    monkeypatch.setattr("rate_limit.monotonic", lambda: next(ticks))
    limiter = InMemoryRateLimiter()

    assert limiter.retry_after("user-1", limit=2, window_seconds=60) is None
    assert limiter.retry_after("user-1", limit=2, window_seconds=60) is None
    assert limiter.retry_after("user-1", limit=2, window_seconds=60) == 58


def test_limiter_keeps_users_in_separate_buckets(monkeypatch):
    monkeypatch.setattr("rate_limit.monotonic", lambda: 100.0)
    limiter = InMemoryRateLimiter()

    assert limiter.retry_after("user-1", limit=1) is None
    assert limiter.retry_after("user-1", limit=1) is not None
    assert limiter.retry_after("user-2", limit=1) is None