"""Focused security tests for webhook/n8n settings and local replay bounds."""

from __future__ import annotations

import time
from typing import Any

import pytest

from app.api.v1.endpoints import webhooks
from app.core.config import LOCAL_APP_ENVS, Settings

_BASE = "https://n8n.example.com"


@pytest.mark.parametrize(
    "field", ["WEBHOOK_TIMESTAMP_SKEW_SECONDS", "WEBHOOK_REPLAY_TTL_SECONDS"]
)
@pytest.mark.parametrize("value", [0, -1])
def test_webhook_bounds_must_be_positive(field: str, value: int) -> None:
    with pytest.raises(RuntimeError, match=field):
        Settings.model_validate({field: value}).validate_runtime()


def test_webhook_bounds_defaults_pass_runtime_validation() -> None:
    settings = Settings()
    assert settings.WEBHOOK_TIMESTAMP_SKEW_SECONDS == 300
    assert settings.WEBHOOK_REPLAY_TTL_SECONDS == 600
    settings.validate_runtime()


@pytest.mark.parametrize("app_env", ["staging", "qa", "production", "totally-unknown"])
def test_deployed_n8n_dispatch_requires_signing_secret(app_env: str) -> None:
    settings = Settings(
        APP_ENV=app_env,
        REDIS_URL="redis://cache:6379/0",
        N8N_BASE_URL=_BASE,
    )
    with pytest.raises(RuntimeError, match="N8N_WEBHOOK_SECRET"):
        settings.validate_runtime()


@pytest.mark.parametrize("app_env", sorted(LOCAL_APP_ENVS))
def test_local_n8n_dispatch_may_omit_signing_secret(app_env: str) -> None:
    settings = Settings(APP_ENV=app_env, N8N_BASE_URL=_BASE)
    settings.validate_runtime()


def test_deployed_n8n_dispatch_with_secret_passes_runtime_validation() -> None:
    settings = Settings(
        APP_ENV="staging",
        REDIS_URL="redis://cache:6379/0",
        N8N_BASE_URL=_BASE,
        N8N_WEBHOOK_SECRET="a-long-test-signing-secret",
    )
    settings.validate_runtime()


def _production_overrides(**extra: Any) -> dict[str, Any]:
    base: dict[str, Any] = dict(
        APP_ENV="production",
        APP_DEBUG=False,
        SECRET_KEY="z" * 32,
        DATABASE_URL="postgresql://u:p@db:5432/app",
        WORKER_DATABASE_URL="postgresql://u:p@db:5432/app",
        CREDENTIALS_ENC_KEY="c2VjcmV0LW1hc3Rlci1rZXktZm9yLXRlc3Rpbmctb25seQ==",
        EMAIL_VERIFICATION_ENABLED=True,
        MFA_ENABLED=True,
        SMTP_HOST="smtp.example.com",
        SMTP_FROM_EMAIL="no-reply@example.com",
        REDIS_URL="redis://cache:6379/0",
        N8N_BASE_URL=_BASE,
    )
    base.update(extra)
    return base


def test_production_validation_requires_n8n_signing_secret() -> None:
    with pytest.raises(RuntimeError, match="N8N_WEBHOOK_SECRET"):
        Settings(**_production_overrides()).validate_for_production()


def test_production_validation_accepts_n8n_signing_secret() -> None:
    settings = Settings(
        **_production_overrides(N8N_WEBHOOK_SECRET="a-long-test-signing-secret")
    )
    settings.validate_for_production()


async def test_local_replay_store_is_bounded_and_prunes_expired(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(webhooks.settings, "APP_ENV", "test")
    now = time.monotonic()
    monkeypatch.setattr(
        webhooks,
        "_replay_seen",
        {f"expired-{i}": now - 1 for i in range(webhooks._MAX_MEMORY_REPLAY_KEYS)},
    )
    assert await webhooks._reserve_replay("acme", "nonce-abcdef123456") is True
    assert len(webhooks._replay_seen) == 1
    assert await webhooks._reserve_replay("acme", "nonce-abcdef123456") is False


async def test_local_replay_store_evicts_when_full(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(webhooks.settings, "APP_ENV", "test")
    now = time.monotonic()
    monkeypatch.setattr(
        webhooks,
        "_replay_seen",
        {
            f"live-{i}": now + 3600 + i
            for i in range(webhooks._MAX_MEMORY_REPLAY_KEYS)
        },
    )
    assert await webhooks._reserve_replay("acme", "nonce-fedcba654321") is True
    assert len(webhooks._replay_seen) == webhooks._MAX_MEMORY_REPLAY_KEYS
