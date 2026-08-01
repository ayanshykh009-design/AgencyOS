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
