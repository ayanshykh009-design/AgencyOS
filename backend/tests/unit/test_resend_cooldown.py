"""Unit tests for the atomic per-email resend cooldown (R2).

The Redis integration suite proves atomicity across instances; these tests pin
the semantics with a deterministic clock: first attempt, repeat suppression,
window expiry, normalization, independence, key privacy, and fail-closed
behaviour when the store is unavailable.
"""

from __future__ import annotations

import asyncio
import hashlib

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.config import LOCAL_APP_ENVS, settings
from app.services.resend_cooldown import (
    CooldownStoreUnavailable,
    EmailResendCooldown,
    InMemoryCooldownBackend,
    RedisCooldownBackend,
    normalize_email,
    reset_default_cooldown_state,
)

SECRET = "unit-test-secret-key"


class _Clock:
    """Mutable monotonic clock so expiry tests never sleep."""

    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _cooldown(clock: _Clock | None = None, *, seconds: int = 60) -> EmailResendCooldown:
    backend = InMemoryCooldownBackend(clock=clock or _Clock())
    return EmailResendCooldown(backend, cooldown_seconds=seconds, secret=SECRET)


@pytest.mark.asyncio
async def test_first_attempt_is_allowed_and_repeat_is_suppressed() -> None:
    gate = _cooldown()

    assert await gate.reserve("owner@example.com") is True
    assert await gate.reserve("owner@example.com") is False


@pytest.mark.asyncio
async def test_attempt_is_allowed_again_after_the_window_expires() -> None:
    clock = _Clock()
    gate = _cooldown(clock)

    assert await gate.reserve("owner@example.com") is True
    clock.advance(59.9)
    assert await gate.reserve("owner@example.com") is False
    clock.advance(0.2)
    assert await gate.reserve("owner@example.com") is True


@pytest.mark.asyncio
async def test_suppressed_attempt_does_not_extend_the_window() -> None:
    """A blocked retry must not push the next allowed attempt further out."""
    clock = _Clock()
    gate = _cooldown(clock)

    assert await gate.reserve("owner@example.com") is True
    clock.advance(59.0)
    assert await gate.reserve("owner@example.com") is False
    clock.advance(1.1)
    assert await gate.reserve("owner@example.com") is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "variant",
    [
        " Owner@Example.com ",
        "OWNER@EXAMPLE.COM",
        "Owner@Example.Com",
        "owner@example.com",
    ],
)
async def test_equivalent_normalized_forms_share_one_window(variant: str) -> None:
    gate = _cooldown()

    assert await gate.reserve("owner@example.com") is True
    assert await gate.reserve(variant) is False


@pytest.mark.asyncio
async def test_different_addresses_have_independent_windows() -> None:
    gate = _cooldown()

    assert await gate.reserve("owner@example.com") is True
    assert await gate.reserve("other@example.com") is True
    assert await gate.reserve("owner@example.com") is False
    assert await gate.reserve("other@example.com") is False


@pytest.mark.asyncio
async def test_concurrent_attempts_have_exactly_one_winner() -> None:
    gate = _cooldown()
    email = "owner@example.com"

    results = await asyncio.gather(*(gate.reserve(email) for _ in range(50)))

    assert results.count(True) == 1
    assert results.count(False) == 49


def test_storage_key_is_keyed_opaque_and_stable() -> None:
    gate = _cooldown()
    key = gate.storage_key("Owner@Example.com")

    # The raw address (or any part of it) never appears in the key.
    assert "owner" not in key
    assert "example" not in key
    assert "@" not in key
    # Normalization matches the lookup rule, so all forms map to one key.
    assert key == gate.storage_key("  owner@example.com ")
    # This is a *keyed* HMAC, not a bare digest an attacker could precompute.
    digest = key.rsplit(":", 1)[1]
    assert digest != hashlib.sha256(normalize_email("Owner@Example.com").encode()).hexdigest()
    # Domain separation: a different secret produces a different key.
    other_secret = EmailResendCooldown(
        InMemoryCooldownBackend(), cooldown_seconds=60, secret="other-secret"
    )
    assert other_secret.storage_key("owner@example.com") != key


def test_normalize_email_matches_the_account_lookup_rule() -> None:
    assert normalize_email("  Owner@Example.COM  ") == "owner@example.com"


@pytest.mark.asyncio
async def test_store_failure_is_reported_rather_than_failing_open() -> None:
    class _UnavailableBackend:
        async def acquire(self, key: str, ttl_seconds: int) -> bool:
            raise CooldownStoreUnavailable("store down")

    gate = EmailResendCooldown(
        _UnavailableBackend(), cooldown_seconds=60, secret=SECRET
    )

    with pytest.raises(CooldownStoreUnavailable):
        await gate.reserve("owner@example.com")


@pytest.mark.asyncio
async def test_zero_window_disables_the_gate_without_touching_the_store() -> None:
    class _NeverCalledBackend:
        async def acquire(self, key: str, ttl_seconds: int) -> bool:
            raise AssertionError("disabled gate must not touch the store")

    gate = EmailResendCooldown(
        _NeverCalledBackend(), cooldown_seconds=0, secret=SECRET
    )

    assert gate.enabled is False
    assert await gate.reserve("owner@example.com") is True


class _RecordingRedis:
    """Stands in for a redis.asyncio client at the protocol boundary."""

    def __init__(self, *, result: bool | None = True, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls: list[tuple[str, str, bool, int | None]] = []

    async def set(
        self, key: str, value: str, *, nx: bool = False, ex: int | None = None
    ) -> bool | None:
        self.calls.append((key, value, nx, ex))
        if self.error is not None:
            raise self.error
        return self.result


@pytest.mark.asyncio
async def test_redis_backend_uses_one_atomic_set_nx_ex() -> None:
    client = _RecordingRedis(result=True)
    gate = EmailResendCooldown(
        RedisCooldownBackend(client), cooldown_seconds=60, secret=SECRET  # type: ignore[arg-type]
    )

    assert await gate.reserve("owner@example.com") is True

    key, value, nx, ex = client.calls[0]
    assert nx is True
    assert ex == 60
    assert key == gate.storage_key("owner@example.com")
    assert value == "1"
    assert "owner@example.com" not in key


@pytest.mark.asyncio
async def test_redis_backend_maps_a_lost_connection_to_store_unavailable() -> None:
    client = _RecordingRedis(error=RedisConnectionError("connection refused"))
    gate = EmailResendCooldown(
        RedisCooldownBackend(client), cooldown_seconds=60, secret=SECRET  # type: ignore[arg-type]
    )

    with pytest.raises(CooldownStoreUnavailable):
        await gate.reserve("owner@example.com")


@pytest.mark.asyncio
@pytest.mark.parametrize("app_env", sorted(LOCAL_APP_ENVS))
async def test_default_backend_uses_memory_only_in_explicit_local_envs(
    monkeypatch: pytest.MonkeyPatch, app_env: str
) -> None:
    """Development/test keep the supported process-local fallback."""
    monkeypatch.setattr(settings, "APP_ENV", app_env)
    monkeypatch.setattr(settings, "REDIS_URL", "")
    reset_default_cooldown_state()

    gate = EmailResendCooldown(cooldown_seconds=60, secret=SECRET)

    assert await gate.reserve("owner@example.com") is True
    assert await gate.reserve("owner@example.com") is False


@pytest.mark.asyncio
@pytest.mark.parametrize("app_env", ["staging", "qa", "production", "totally-unknown"])
async def test_default_backend_fails_closed_outside_local_envs(
    monkeypatch: pytest.MonkeyPatch,
    app_env: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A deployed environment without shared Redis must not enforce per-process.

    Boot validation rejects this configuration; the backend selection is the
    second layer, so a bypassed lifespan still fails closed rather than sending
    mail behind a cooldown that only exists inside one replica.
    """
    monkeypatch.setattr(settings, "APP_ENV", app_env)
    monkeypatch.setattr(settings, "REDIS_URL", "")
    reset_default_cooldown_state()

    with caplog.at_level("ERROR", logger="agencyos.resend_cooldown"):
        gate = EmailResendCooldown(cooldown_seconds=60, secret=SECRET)

    with pytest.raises(CooldownStoreUnavailable):
        await gate.reserve("owner@example.com")

    assert "shared store required" in caplog.text
    assert "owner@example.com" not in caplog.text


