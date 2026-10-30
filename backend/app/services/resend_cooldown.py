"""Atomic per-email cooldown for verification-resend attempts (R2).

Policy: at most one resend attempt per normalized email address per rolling
window (``EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS``; at least 60s in every
deployed environment, 0 disables it only in development/test).

Atomicity: the production backend issues a single Redis ``SET key 1 NX EX ttl``.
Acquisition is one server-side round-trip, so two concurrent requests can never
both observe "allowed" — a ``GET`` followed by a ``SET`` would race and is
deliberately not used.

Privacy: Redis keys are keyed HMAC-SHA256 digests of the normalized address with
a fixed domain-separation label. The raw address never reaches Redis, logs,
metrics, errors, or responses. ``SECRET_KEY`` (required to be strong in
production) is the HMAC key.

The process-local backend exists for development and tests only. It is
selectable only for the explicit ``LOCAL_APP_ENVS`` allow-list; every other
environment (staging, QA, production, or an unknown value) requires shared
Redis at boot and fails closed if the shared store is somehow missing.

Failure behaviour: a store failure raises :class:`CooldownStoreUnavailable`;
callers must fail closed (suppress the resend) rather than send without the
control in place.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import threading
import time
from collections.abc import Callable
from typing import Protocol

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.redis import RedisNotConfiguredError, get_redis

logger = logging.getLogger("agencyos.resend_cooldown")

_KEY_PREFIX = "agencyos:auth:resend-cooldown:v1"
_DOMAIN_SEPARATION = b"agencyos:email-verification-resend:v1"
_MEMORY_SWEEP_THRESHOLD = 1024


class CooldownStoreUnavailable(RuntimeError):
    """The shared cooldown store could not answer; callers must fail closed."""


class CooldownBackend(Protocol):
    """Minimal atomic reservation interface."""

    async def acquire(self, key: str, ttl_seconds: int) -> bool:
        """Reserve ``key`` for ``ttl_seconds``; return False if already held."""
        ...


class RedisCooldownBackend:
    """Atomic ``SET NX EX`` reservation against the shared Redis deployment."""

    def __init__(self, client: Redis | None = None) -> None:
        # Injecting a client lets tests (and future call sites) share an
        # explicitly managed connection instead of the process-wide one.
        self._client = client

    def _connection(self) -> Redis:
        return self._client if self._client is not None else get_redis()

    async def acquire(self, key: str, ttl_seconds: int) -> bool:
        try:
            acquired = await self._connection().set(key, "1", nx=True, ex=ttl_seconds)
        except (RedisError, OSError, RedisNotConfiguredError) as exc:
            raise CooldownStoreUnavailable("resend cooldown store unavailable") from exc
        return bool(acquired)


class InMemoryCooldownBackend:
    """Process-local fallback for development/tests only (never deployed).

    The critical section is synchronous under a mutex, so it is atomic within a
    process. It is *not* shared across workers; it is only selectable in the
    explicit development/test allow-list (``LOCAL_APP_ENVS``).
    """

    def __init__(self, clock: Callable[[], float] | None = None) -> None:
        self._clock = clock or time.monotonic
        self._lock = threading.Lock()
        self._expiries: dict[str, float] = {}

    async def acquire(self, key: str, ttl_seconds: int) -> bool:
        now = self._clock()
        with self._lock:
            expiry = self._expiries.get(key)
            if expiry is not None and expiry > now:
                return False
            self._expiries[key] = now + ttl_seconds
            if len(self._expiries) > _MEMORY_SWEEP_THRESHOLD:
                self._expiries = {
                    stored: expires
                    for stored, expires in self._expiries.items()
                    if expires > now
                }
            return True

    def reset(self) -> None:
        """Forget every reservation (test isolation helper)."""
        with self._lock:
            self._expiries.clear()


class UnavailableCooldownBackend:
    """Fail-closed backend for deployed environments without shared Redis.

    Defence in depth: startup validation refuses to boot such configurations,
    but if a service is constructed anyway (a code path that bypasses the app
    lifespan, or a bad deploy) the gate must never silently degrade to
    per-process memory. Every attempt reports the store as unavailable so the
    caller suppresses the resend.
    """

    async def acquire(self, key: str, ttl_seconds: int) -> bool:
        raise CooldownStoreUnavailable(
            "shared Redis is required for the resend cooldown in this environment"
        )


_default_backend: CooldownBackend | None = None


def _get_default_backend() -> CooldownBackend:
    """Return the process-wide backend, preferring shared Redis when configured.

    The in-memory backend is restricted to the explicit development/test
    allow-list. Any other environment without ``REDIS_URL`` gets a backend that
    fails closed instead of a per-process cooldown that would look healthy while
    enforcing nothing across replicas.
    """
    global _default_backend
    if _default_backend is None:
        if settings.REDIS_URL:
            _default_backend = RedisCooldownBackend()
        elif settings.is_local_environment:
            logger.warning(
                "auth.resend.cooldown using process-local backend; "
                "REDIS_URL is required outside development/test"
            )
            _default_backend = InMemoryCooldownBackend()
        else:
            logger.error(
                "auth.resend.cooldown shared store required but REDIS_URL is unset "
                "(app_env=%s); failing closed",
                settings.APP_ENV,
            )
            _default_backend = UnavailableCooldownBackend()
    return _default_backend


def reset_default_cooldown_state() -> None:
    """Drop the cached default backend and clear memory state (test helper)."""
    global _default_backend
    backend = _default_backend
    if isinstance(backend, InMemoryCooldownBackend):
        backend.reset()
    _default_backend = None


def normalize_email(email: str) -> str:
    """Canonical address form, matching registration/login and lookups."""
    return str(email).strip().lower()


class EmailResendCooldown:
    """One verification-resend attempt per normalized address per window."""

    def __init__(
        self,
        backend: CooldownBackend | None = None,
        *,
        cooldown_seconds: int | None = None,
        secret: str | None = None,
    ) -> None:
        self._backend = backend if backend is not None else _get_default_backend()
        self._cooldown_seconds = (
            settings.EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS
            if cooldown_seconds is None
            else cooldown_seconds
        )
        self._secret = (settings.SECRET_KEY if secret is None else secret).encode("utf-8")

    @property
    def enabled(self) -> bool:
        """A zero window disables the gate (development only in practice)."""
        return self._cooldown_seconds > 0

    def storage_key(self, email: str) -> str:
        """Return the opaque, keyed storage key for ``email``.

        The fixed label provides domain separation: a digest produced here can
        never collide with another use of ``SECRET_KEY`` even for the same input.
        """
        digest = hmac.new(
            self._secret,
            _DOMAIN_SEPARATION + b":" + normalize_email(email).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return f"{_KEY_PREFIX}:{digest}"

    async def reserve(self, email: str) -> bool:
        """Consume one attempt for ``email``; raise when the store is unavailable."""
        if not self.enabled:
            return True
        return await self._backend.acquire(self.storage_key(email), self._cooldown_seconds)
