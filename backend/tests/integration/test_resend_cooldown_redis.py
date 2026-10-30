"""Real-Redis integration tests for the per-email resend cooldown (R2).

Mocks cannot prove a distributed `SET NX EX`: these tests use two independent
Redis clients to model two application instances sharing one store. They run in
CI (which provides a Redis service via ``TEST_REDIS_URL``) and skip cleanly on a
developer machine without Redis.

Coverage: cross-instance sharing, concurrent single-winner reservations, real
key expiry, normalized forms, opaque keys, and fail-closed behaviour when the
store is unreachable.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator

import pytest

pytest.importorskip("redis")
from redis.asyncio import Redis  # noqa: E402

from app.services.resend_cooldown import (  # noqa: E402
    CooldownStoreUnavailable,
    EmailResendCooldown,
    RedisCooldownBackend,
)

TEST_REDIS_URL = os.getenv("TEST_REDIS_URL", "")
SECRET = "integration-test-secret"

# Skip only when no URL is configured (developer machine). In CI the URL is
# always set, so an unreachable server fails the suite instead of silently
# skipping the distributed guarantee.
pytestmark = pytest.mark.skipif(
    not TEST_REDIS_URL, reason="TEST_REDIS_URL is not configured"
)


def _email() -> str:
    return f"owner-{uuid.uuid4().hex}@example.com"


@pytest.fixture()
async def clients() -> AsyncIterator[tuple[Redis, Redis]]:
    """Two separate connections, standing in for two application instances."""
    first = Redis.from_url(TEST_REDIS_URL, decode_responses=True, socket_connect_timeout=2)
    second = Redis.from_url(TEST_REDIS_URL, decode_responses=True, socket_connect_timeout=2)
    try:
        yield first, second
    finally:
        await first.aclose()
        await second.aclose()


@pytest.mark.asyncio
async def test_two_instances_share_one_window(clients: tuple[Redis, Redis]) -> None:
    first_client, second_client = clients
    email = _email()
    first = EmailResendCooldown(RedisCooldownBackend(first_client), secret=SECRET)
    second = EmailResendCooldown(RedisCooldownBackend(second_client), secret=SECRET)
    key = first.storage_key(email)
    try:
        assert await first.reserve(email) is True
        assert await second.reserve(email) is False
        ttl = await first_client.ttl(key)
        assert 0 < ttl <= 60
    finally:
        await first_client.delete(key)


@pytest.mark.asyncio
async def test_concurrent_reservations_have_exactly_one_winner(
    clients: tuple[Redis, Redis],
) -> None:
    first_client, second_client = clients
    gates = [
        EmailResendCooldown(RedisCooldownBackend(first_client), secret=SECRET),
        EmailResendCooldown(RedisCooldownBackend(second_client), secret=SECRET),
    ]
    for _ in range(10):
        email = _email()
        key = gates[0].storage_key(email)
        try:
            results = await asyncio.gather(
                *(gates[index % 2].reserve(email) for index in range(20))
            )
            assert results.count(True) == 1, results
            assert results.count(False) == 19, results
        finally:
            await first_client.delete(key)


@pytest.mark.asyncio
async def test_expiry_allows_another_attempt(clients: tuple[Redis, Redis]) -> None:
    client, _ = clients
    email = _email()
    gate = EmailResendCooldown(
        RedisCooldownBackend(client), cooldown_seconds=2, secret=SECRET
    )
    key = gate.storage_key(email)
    try:
        assert await gate.reserve(email) is True
        assert await gate.reserve(email) is False
        # Wait for the real TTL to elapse instead of sleeping a full minute.
        for _ in range(60):
            if not await client.exists(key):
                break
            await asyncio.sleep(0.1)
        else:
            pytest.fail("cooldown key did not expire")
        assert await gate.reserve(email) is True
    finally:
        await client.delete(key)


@pytest.mark.asyncio
async def test_normalized_forms_share_one_key(clients: tuple[Redis, Redis]) -> None:
    first_client, second_client = clients
    email = _email()
    first = EmailResendCooldown(RedisCooldownBackend(first_client), secret=SECRET)
    second = EmailResendCooldown(RedisCooldownBackend(second_client), secret=SECRET)
    key = first.storage_key(email)
    try:
        assert await first.reserve(email) is True
        assert await second.reserve(f"  {email.upper()}  ") is False
        assert await first_client.exists(key) == 1
    finally:
        await first_client.delete(key)


@pytest.mark.asyncio
async def test_redis_keys_never_contain_the_raw_address(
    clients: tuple[Redis, Redis],
) -> None:
    client, _ = clients
    email = _email()
    gate = EmailResendCooldown(RedisCooldownBackend(client), secret=SECRET)
    key = gate.storage_key(email)
    prefix = key.rsplit(":", 1)[0]
    try:
        assert await gate.reserve(email) is True
        stored = await client.keys(f"{prefix}:*")
        assert key in stored
        assert all(email not in candidate for candidate in stored)
        assert "owner-" not in key
        assert "@example.com" not in key
    finally:
        await client.delete(key)


@pytest.mark.asyncio
async def test_unreachable_store_raises_instead_of_failing_open() -> None:
    unreachable = Redis.from_url(
        "redis://127.0.0.1:1/0",
        socket_connect_timeout=0.25,
        socket_timeout=0.25,
    )
    try:
        gate = EmailResendCooldown(
            RedisCooldownBackend(unreachable), secret=SECRET
        )
        with pytest.raises(CooldownStoreUnavailable):
            await gate.reserve(_email())
    finally:
        await unreachable.aclose()
