"""In-process cache proxy (falls back to dict when Redis is unavailable).

execute_booking results are NEVER cached — see hard constraint 7.
"""

from __future__ import annotations

import json
from typing import Any

# JSON-serialisable value alias — Any is unavoidable here since json.loads
# can return any JSON type.
_JsonValue = Any


class CachedLayer:
    """Tiered cache: tries Redis first, falls back to in-memory dict."""

    def __init__(self, redis_url: str | None = None) -> None:
        self._store: dict[str, str] = {}
        self._redis: Any = None
        if redis_url:
            try:
                import redis.asyncio as aioredis

                self._redis = aioredis.from_url(redis_url, decode_responses=True)
            except Exception:  # noqa: S110 — Redis is optional
                pass

    async def get(self, key: str) -> _JsonValue:
        if self._redis is not None:
            try:
                raw = await self._redis.get(key)
                if raw is not None:
                    return json.loads(raw)
            except Exception:  # noqa: S110 — degrade to in-memory
                pass
        raw = self._store.get(key)
        return json.loads(raw) if raw is not None else None

    async def set(self, key: str, value: _JsonValue, ttl: int = 300) -> None:
        serialised = json.dumps(value)
        self._store[key] = serialised
        if self._redis is not None:
            try:
                await self._redis.set(key, serialised, ex=ttl)
            except Exception:  # noqa: S110 — degrade to in-memory
                pass

    async def close(self) -> None:
        if self._redis is not None:
            try:
                await self._redis.aclose()
            except Exception:  # noqa: S110
                pass


# Module-level default instance (no Redis configured in dev/test)
default_cache = CachedLayer()
