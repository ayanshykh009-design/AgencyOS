"""Tests for configuration parsing and production safeguards."""
import pytest

from app.core.config import Settings


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
        SECRET_KEY="a-strong-secret",
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


def test_development_skips_production_validation() -> None:
    settings = Settings(
        APP_ENV="development",
        APP_DEBUG=True,
        SECRET_KEY="change-me",
        DATABASE_URL="postgresql+asyncpg://u:p@db:5432/app",
    )
    settings.validate_for_production()  # must not raise


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
        SECRET_KEY="a-strong-secret",
        DATABASE_URL="postgresql+asyncpg://u:p@db:5432/app",
        REDIS_URL="sqlite:///rate.db",
    )
    with pytest.raises(RuntimeError, match="REDIS_URL"):
        settings.validate_for_production()
