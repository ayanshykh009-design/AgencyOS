"""Shared async Redis client for security state that must span instances.

The rate limiter (slowapi/limits) owns its own connection; this module is the
application-level async client for state that must be identical across every
worker — currently the per-email verification-resend cooldown.

The client is created lazily on first use and closed during application
shutdown. ``REDIS_URL`` is mandatory in production (see
``Settings.validate_for_production``); outside production a missing URL is
reported to the caller so it can choose an explicit, documented fallback.
"""

from __future__ import annotations

from redis.asyncio import Redis, from_url

from app.core.config import settings

_client: Redis | None = None


class RedisNotConfiguredError(RuntimeError):
    """Raised when shared Redis is required but ``REDIS_URL`` is empty."""


def get_redis() -> Redis:
    """Return the process-wide async Redis client, creating it on first use."""
    global _client
    if _client is None:
        if not settings.REDIS_URL:
            raise RedisNotConfiguredError("REDIS_URL is not configured")
        _client = from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
    return _client


async def close_redis() -> None:
    """Close the shared client (safe to call when it was never created)."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
