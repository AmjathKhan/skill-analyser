"""Sliding-window rate limiting backed by Redis, with an in-process fallback."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(slots=True)
class RateLimitVerdict:
    allowed: bool
    remaining: int
    retry_after: int


class _MemoryBackend:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window: int) -> RateLimitVerdict:
        now = time.time()
        with self._lock:
            bucket = self._hits[key]
            cutoff = now - window
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                retry_after = max(1, int(window - (now - bucket[0])))
                return RateLimitVerdict(False, 0, retry_after)
            bucket.append(now)
            return RateLimitVerdict(True, max(0, limit - len(bucket)), 0)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


class _RedisBackend:
    def __init__(self, url: str) -> None:
        import redis  # imported lazily so redis stays optional at runtime

        self._client = redis.Redis.from_url(url, socket_connect_timeout=1, socket_timeout=1)
        self._client.ping()

    def hit(self, key: str, limit: int, window: int) -> RateLimitVerdict:
        now = time.time()
        redis_key = f"ratelimit:{key}"
        pipe = self._client.pipeline()
        pipe.zremrangebyscore(redis_key, 0, now - window)
        pipe.zadd(redis_key, {f"{now}:{id(pipe)}": now})
        pipe.zcard(redis_key)
        pipe.expire(redis_key, window + 1)
        _, _, count, _ = pipe.execute()
        if int(count) > limit:
            return RateLimitVerdict(False, 0, window)
        return RateLimitVerdict(True, max(0, limit - int(count)), 0)

    def reset(self) -> None:
        for key in self._client.scan_iter("ratelimit:*"):
            self._client.delete(key)


class RateLimiter:
    """Chooses Redis when reachable, otherwise degrades to per-process limiting."""

    def __init__(self) -> None:
        self._backend: _MemoryBackend | _RedisBackend
        try:
            self._backend = _RedisBackend(settings.redis_url)
            logger.info("rate limiter using Redis at %s", settings.redis_url)
        except Exception as exc:
            logger.warning("rate limiter falling back to memory backend (%s)", exc.__class__.__name__)
            self._backend = _MemoryBackend()

    def check(self, key: str, *, limit: int, window: int) -> RateLimitVerdict:
        if not settings.rate_limit_enabled:
            return RateLimitVerdict(True, limit, 0)
        try:
            return self._backend.hit(key, limit, window)
        except Exception as exc:
            logger.warning("rate limiter error, allowing request: %s", exc)
            return RateLimitVerdict(True, limit, 0)

    def reset(self) -> None:
        self._backend.reset()


_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = RateLimiter()
    return _limiter
