"""Small process-local rate limiter for authenticated model-backed requests."""

from collections import defaultdict, deque
from threading import Lock
from time import monotonic


class InMemoryRateLimiter:
    """Sliding-window limiter; use a shared store before running multiple workers."""

    def __init__(self) -> None:
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def retry_after(
        self, key: str, *, limit: int = 10, window_seconds: int = 60,
    ) -> int | None:
        now = monotonic()
        cutoff = now - window_seconds
        with self._lock:
            timestamps = self._requests[key]
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()
            if not timestamps:
                self._requests.pop(key, None)
                timestamps = self._requests[key]
            if len(timestamps) >= limit:
                return max(1, int(timestamps[0] + window_seconds - now + 0.999))
            timestamps.append(now)
            return None