"""Tests for configuration parsing and production safeguards."""
import pytest

from app.core.config import DEFAULT_SECRET_KEY, Settings

# A deliberately strong, non-default production secret (>= 32 chars).
STRONG_SECRET = (
    "a-very-long-production-secret-key-that-exceeds-thirty-two-characters-1234567890"
)



def test_cors_origins_parsing() -> None:
    settings = Settings(CORS_ORIGINS="http://a.local, https://b.local, ,")
    assert settings.cors_origins_list == ["http://a.local", "https://b.local"]


def test_trusted_hosts_parsing() -> None:
    settings = Settings(TRUSTED_HOSTS="localhost, api.example.com")
    assert settings.trusted_hosts_list == ["localhost", "api.example.com"]


def test_production_validation_rejects_debug() -> None:
    settings = Settings(
        APP_ENV="production",
        APP_DEBUG=True,
        SECRET_KEY=STRONG_SECRET,
        DATABASE_URL="postgresql+asyncpg://u:p@db:5432/app",
    )
    with pytest.raises(RuntimeError, match="APP_DEBUG"):
        settings.validate_for_production()


def test_production_validation_rejects_default_secret() -> None:
    settings = Settings(
        APP_ENV="production",
        APP_DEBUG=False,
        SECRET_KEY="change-me",
        DATABASE_URL="postgresql+asyncpg://u:p@db:5432/app",
    )
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        settings.validate_for_production()


def test_production_validation_rejects_hardcoded_dev_secret() -> None:
    settings = Settings(
        APP_ENV="production",
        APP_DEBUG=False,
        SECRET_KEY=DEFAULT_SECRET_KEY,
        DATABASE_URL="postgresql+asyncpg://u:p@db:5432/app",
    )
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        settings.validate_for_production()


def test_production_validation_rejects_short_weak_secret() -> None:
    settings = Settings(
        APP_ENV="production",
        APP_DEBUG=False,
        SECRET_KEY="short",
        DATABASE_URL="postgresql+asyncpg://u:p@db:5432/app",
    )
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        settings.validate_for_production()


def test_production_validation_rejects_empty_secret() -> None:
    settings = Settings(
        APP_ENV="production",
        APP_DEBUG=False,
        SECRET_KEY="",
        DATABASE_URL="postgresql+asyncpg://u:p@db:5432/app",
    )
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        settings.validate_for_production()


def test_production_validation_accepts_strong_secret() -> None:
    settings = Settings(
        APP_ENV="production",
        APP_DEBUG=False,
        SECRET_KEY=STRONG_SECRET,
        DATABASE_URL="postgresql+asyncpg://u:p@db:5432/app",
        CREDENTIALS_ENC_KEY="Zk9x7mW3pQ2vRtY8uB1cN4dL6eF0gH5jAbCdEfGhIjKl",
    )
    settings.validate_for_production()  # must not raise


def test_secret_key_default_is_dev_scoped() -> None:
    # The default is a known, committed dev/test value; production rejects it.
    assert Settings().SECRET_KEY == DEFAULT_SECRET_KEY
    dev = Settings(APP_ENV="development")
    dev.validate_for_production()  # no-op outside production
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        Settings(
            APP_ENV="production", APP_DEBUG=False, SECRET_KEY=DEFAULT_SECRET_KEY
        ).validate_for_production()


def test_development_skips_production_validation() -> None:
    settings = Settings(
        APP_ENV="development",
        APP_DEBUG=True,
        SECRET_KEY="change-me",
        DATABASE_URL="postgresql+asyncpg://u:p@db:5432/app",
    )
    settings.validate_for_production()  # must not raise


def test_production_risk_flags_default_off() -> None:
    # Fail-closed: production-risk AI/automation flags must default OFF.
    settings = Settings()
    assert settings.DELIVERY_ENABLED is False
    assert settings.FOUNDER_ASSISTANT_ENABLED is False



def test_validate_rejects_bad_redis_scheme() -> None:
    settings = Settings(REDIS_URL="mysql://localhost:3306/cache")
    with pytest.raises(RuntimeError, match="REDIS_URL"):
        settings.validate_runtime()


def test_validate_accepts_empty_and_valid_redis() -> None:
    Settings(REDIS_URL="").validate_runtime()
    Settings(REDIS_URL="redis://localhost:6379/0").validate_runtime()
    Settings(REDIS_URL="rediss://cache.internal:6379/0").validate_runtime()


def test_production_validation_rejects_bad_redis() -> None:
    settings = Settings(
        APP_ENV="production",
        APP_DEBUG=False,
        SECRET_KEY=STRONG_SECRET,
        DATABASE_URL="postgresql+asyncpg://u:p@db:5432/app",
        REDIS_URL="sqlite:///rate.db",
        CREDENTIALS_ENC_KEY="Zk9x7mW3pQ2vRtY8uB1cN4dL6eF0gH5jAbCdEfGhIjKl",
    )
    with pytest.raises(RuntimeError, match="REDIS_URL"):
        settings.validate_for_production()


def test_phase5d_validation_rejects_zero_ttl() -> None:
    settings = Settings(MEMORY_WORKING_TTL_DAYS=0)
    with pytest.raises(RuntimeError, match="MEMORY_WORKING_TTL_DAYS"):
        settings.validate_runtime()


def test_phase5d_validation_rejects_zero_notification_retention() -> None:
    settings = Settings(NOTIFICATION_RETENTION_DAYS=0)
    with pytest.raises(RuntimeError, match="NOTIFICATION_RETENTION_DAYS"):
        settings.validate_runtime()


def test_phase5d_validation_rejects_zero_approval_expiry() -> None:
    settings = Settings(APPROVAL_EXPIRY_HOURS=0)
    with pytest.raises(RuntimeError, match="APPROVAL_EXPIRY_HOURS"):
        settings.validate_runtime()


def test_phase5d_validation_rejects_zero_growth_retention() -> None:
    settings = Settings(GROWTH_METRICS_RETENTION_DAYS=0)
    with pytest.raises(RuntimeError, match="GROWTH_METRICS_RETENTION_DAYS"):
        settings.validate_runtime()


def test_m4_validation_rejects_short_cleanup_interval() -> None:
    settings = Settings(MEMORY_CLEANUP_INTERVAL_SECONDS=30)
    with pytest.raises(RuntimeError, match="MEMORY_CLEANUP_INTERVAL_SECONDS"):
        settings.validate_runtime()


def test_m4_validation_rejects_zero_batch_size() -> None:
    settings = Settings(MEMORY_CLEANUP_BATCH_SIZE=0)
    with pytest.raises(RuntimeError, match="MEMORY_CLEANUP_BATCH_SIZE"):
        settings.validate_runtime()


def test_m4_validation_rejects_small_context_budget() -> None:
    settings = Settings(MEMORY_CONTEXT_MAX_CHARS=100)
    with pytest.raises(RuntimeError, match="MEMORY_CONTEXT_MAX_CHARS"):
        settings.validate_runtime()


def test_m4_validation_rejects_zero_retrieval_limit() -> None:
    settings = Settings(MEMORY_RETRIEVAL_LIMIT=0)
    with pytest.raises(RuntimeError, match="MEMORY_RETRIEVAL_LIMIT"):
        settings.validate_runtime()


def test_m4_defaults_pass_runtime_validation() -> None:
    Settings().validate_runtime()  # must not raise


def test_phase5d_defaults_pass_runtime_validation() -> None:
    Settings().validate_runtime()  # must not raise


def test_m9_validation_rejects_short_triage_interval() -> None:
    settings = Settings(INTELLIGENCE_TRIAGE_INTERVAL_SECONDS=30)
    with pytest.raises(RuntimeError, match="INTELLIGENCE_TRIAGE_INTERVAL_SECONDS"):
        settings.validate_runtime()


def test_m9_validation_rejects_zero_max_signals() -> None:
    settings = Settings(INTELLIGENCE_TRIAGE_MAX_SIGNALS_PER_ORG=0)
    with pytest.raises(RuntimeError, match="INTELLIGENCE_TRIAGE_MAX_SIGNALS_PER_ORG"):
        settings.validate_runtime()


def test_m9_validation_rejects_zero_window_days() -> None:
    settings = Settings(INTELLIGENCE_TRIAGE_WINDOW_DAYS=0)
    with pytest.raises(RuntimeError, match="INTELLIGENCE_TRIAGE_WINDOW_DAYS"):
        settings.validate_runtime()


def test_m9_validation_rejects_zero_orgs_per_sweep() -> None:
    settings = Settings(INTELLIGENCE_TRIAGE_ORGS_PER_SWEEP=0)
    with pytest.raises(RuntimeError, match="INTELLIGENCE_TRIAGE_ORGS_PER_SWEEP"):
        settings.validate_runtime()


def test_m9_validation_rejects_zero_narrative_top_n() -> None:
    settings = Settings(INTELLIGENCE_NARRATIVE_TOP_N=0)
    with pytest.raises(RuntimeError, match="INTELLIGENCE_NARRATIVE_TOP_N"):
        settings.validate_runtime()


def test_m9_validation_rejects_small_context_budget() -> None:
    settings = Settings(INTELLIGENCE_NARRATIVE_MAX_CONTEXT_CHARS=100)
    with pytest.raises(RuntimeError, match="INTELLIGENCE_NARRATIVE_MAX_CONTEXT_CHARS"):
        settings.validate_runtime()


def test_m9_validation_rejects_negative_retries() -> None:
    settings = Settings(INTELLIGENCE_NARRATIVE_MAX_RETRIES=-1)
    with pytest.raises(RuntimeError, match="INTELLIGENCE_NARRATIVE_MAX_RETRIES"):
        settings.validate_runtime()


def test_m9_defaults_pass_runtime_validation() -> None:
    Settings().validate_runtime()  # must not raise
