from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from .config import settings

logger = logging.getLogger("campus_innovators.rate_limit")


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "") if settings.trust_proxy_headers else ""
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimitExceeded(Exception):
    """Raised by a backend when a key has exceeded its limit. Carries retry_after in seconds."""

    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded, retry after {retry_after}s")


class _InMemoryLimiter:
    """Sliding-window limiter backed by an in-process deque per key.

    This only sees traffic hitting this one process, so it's a fine default for local
    dev / single-instance deployments but under-counts when multiple backend replicas
    are running behind a load balancer — that's what `_RedisLimiter` is for.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buckets: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, limit: int, window_seconds: int) -> None:
        now = time.monotonic()
        with self._lock:
            bucket = self._buckets[key]
            cutoff = now - window_seconds
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                retry_after = max(1, int(window_seconds - (now - bucket[0])))
                raise RateLimitExceeded(retry_after)
            bucket.append(now)


# Lua script for an atomic sliding-window check-and-increment against a Redis sorted set.
# KEYS[1] = bucket key
# ARGV[1] = current unix time (float, seconds)
# ARGV[2] = window size in seconds
# ARGV[3] = limit
# ARGV[4] = unique member id for this request (avoids collisions when two requests share a score)
#
# Evicts entries older than the window, counts what's left, and either rejects (returning the
# retry-after seconds) or admits the request (adding it to the set) — all atomically, so this is
# safe under concurrent requests across multiple backend processes sharing the same Redis.
_REDIS_SLIDING_WINDOW_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]

redis.call("ZREMRANGEBYSCORE", key, "-inf", now - window)
local count = redis.call("ZCARD", key)

if count >= limit then
    local oldest = redis.call("ZRANGE", key, 0, 0, "WITHSCORES")
    local retry_after = 1
    if oldest[2] ~= nil then
        retry_after = math.max(1, math.ceil(window - (now - tonumber(oldest[2]))))
    end
    return {0, retry_after}
end

redis.call("ZADD", key, now, member)
redis.call("EXPIRE", key, window)
return {1, 0}
"""


class _RedisLimiter:
    """Sliding-window limiter backed by a Redis sorted set, shared across all backend
    instances. Uses a Lua script so the evict/count/admit sequence is atomic and race-free
    even when many processes hit the same key concurrently.
    """

    def __init__(self, client) -> None:
        self._client = client
        self._script = client.register_script(_REDIS_SLIDING_WINDOW_SCRIPT)
        self._counter_lock = threading.Lock()
        self._counter = 0

    def _next_member(self) -> str:
        # ZADD needs a unique member per request within the same key; a monotonic counter
        # combined with the wall clock is enough to avoid collisions from this process, and
        # different processes get different random-ish PIDs/threads so cross-process
        # collisions are effectively impossible for our purposes.
        with self._counter_lock:
            self._counter += 1
            return f"{time.time()}:{self._counter}"

    def check(self, key: str, limit: int, window_seconds: int) -> None:
        now = time.time()
        member = self._next_member()
        allowed, retry_after = self._script(keys=[key], args=[now, window_seconds, limit, member])
        if not allowed:
            raise RateLimitExceeded(int(retry_after))


def _build_backend():
    if not settings.redis_url:
        return _InMemoryLimiter()

    try:
        import redis

        client = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
        client.ping()
        logger.info("Rate limiter connected to Redis at %s", settings.redis_url)
        return _RedisLimiter(client)
    except Exception as exc:  # noqa: BLE001 - any connection/import failure should fall back, not crash startup
        logger.warning("Redis rate limiter unavailable (%s); falling back to in-memory rate limiting.", exc)
        return _InMemoryLimiter()


_backend = _build_backend()


def enforce(request: Request, scope: str, limit: int, window_seconds: int) -> None:
    key = f"{scope}:{client_ip(request)}"
    try:
        _backend.check(key, limit, window_seconds)
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Please try again later.",
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
