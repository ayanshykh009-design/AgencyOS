"""M10 production configuration hardening must fail closed.

These tests require no database; they exercise the startup validators in
``app.core.config`` and confirm dangerous production configuration is rejected
and a sane production configuration is accepted.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings


def _prod_settings(**overrides) -> Settings:
    base = dict(
        APP_ENV="production",
        APP_DEBUG=False,
        APP_NAME="AgencyOS API",
        SECRET_KEY="z" * 32,
        DATABASE_URL="postgresql://agencyos:secret@db:5432/agencyos",
        WORKER_DATABASE_URL="postgresql://agencyos:secret@db:5432/agencyos",
        ENABLE_CSP=True,
        CREDENTIALS_ENC_KEY="c2VjcmV0LW1hc3Rlci1rZXktZm9yLXRlc3Rpbmctb25seQ==",
        # Production must run with the account-security controls *enabled* and
        # with SMTP configured, otherwise the mail flows silently no-op.
        EMAIL_VERIFICATION_ENABLED=True,
        MFA_ENABLED=True,
        SMTP_HOST="smtp.example.com",
        SMTP_FROM_EMAIL="no-reply@example.com",
        REDIS_URL="redis://localhost:6379/0",
    )
    base.update(overrides)
    return Settings(**base)


def test_prod_accepts_safe_config():
    # A well-formed production configuration must validate cleanly.
    cfg = _prod_settings()
    assert cfg.validate_for_production() is None


@pytest.mark.parametrize(
    "bad",
    [
        {"APP_DEBUG": True},
        {"SECRET_KEY": "change-me"},
        {"SECRET_KEY": "fhUxAL6v2kWmZpQ9e5jR4tYb7cD1n8mF3oP6q7sT4vW"},
        {"DATABASE_URL": "sqlite:///x.db"},
        # B-3: production must point workers at the BYPASSRLS role explicitly.
        {"WORKER_DATABASE_URL": ""},
        {"WORKER_DATABASE_URL": "sqlite:///x.db"},
        {"ENABLE_CSP": False},
        {"CREDENTIALS_ENC_KEY": ""},
        {"CREDENTIALS_ENC_KEY_PREVIOUS": "rotate-me", "CREDENTIAL_KEY_VERSION": "1"},
        {"CREDENTIAL_KEY_VERSION": "0"},
        # Account-security controls must be active in production, not just built.
        {"EMAIL_VERIFICATION_ENABLED": False},
        {"MFA_ENABLED": False},
        {"SMTP_HOST": ""},
        {"SMTP_FROM_EMAIL": ""},
        # A per-process memory:// limiter dilutes auth throttling across replicas.
        {"REDIS_URL": ""},
        {"REDIS_URL": "ftp://nope"},
        # R2: the per-email resend cooldown must not be silently disabled.
        {"EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS": 0},
        {"EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS": 59},
    ],
)
def test_prod_rejects_unsafe_config(bad):
    with pytest.raises(RuntimeError):
        _prod_settings(**bad).validate_for_production()


def test_validate_runtime_rejects_bad_redis_url():
    with pytest.raises(RuntimeError):
        Settings(REDIS_URL="ftp://nope").validate_runtime()


def test_validate_runtime_accepts_default():
    # Default (dev) configuration must pass the always-on runtime checks.
    assert Settings().validate_runtime() is None


def test_production_flag_gate():
    # Non-production must short-circuit without raising regardless of secrets.
    assert Settings(APP_ENV="test", SECRET_KEY="change-me").validate_for_production() is None
