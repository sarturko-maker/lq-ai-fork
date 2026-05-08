"""Async Redis client for the api/ service.

Used (in later tasks) for sessions, rate-limit token buckets, and the
document-pipeline queue. Here in A4 the surface is just enough for the
readiness probe.

`redis.asyncio` is the asyncio variant of redis-py; the package name on
PyPI is just `redis`. The constructor is non-blocking — actual TCP
connection happens on first command.
"""

from __future__ import annotations

import logging

from redis import asyncio as aioredis
from redis.asyncio import Redis

from app.config import get_settings

log = logging.getLogger(__name__)

_client: Redis | None = None


def get_redis() -> Redis:
    """Return the process-global async Redis client, building it on first call."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _client


async def check_redis() -> bool:
    """Readiness check: returns True if Redis responds to PING."""
    try:
        client = get_redis()
        pong = await client.ping()
        return bool(pong)
    except Exception as exc:
        # Readiness probes never raise — surface failure in the response body.
        log.warning("Redis readiness check failed: %s", exc)
        return False


async def close_redis() -> None:
    """Close the Redis client on shutdown."""
    global _client
    if _client is not None:
        await _client.aclose()
    _client = None
