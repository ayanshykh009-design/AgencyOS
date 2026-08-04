"""Tests for the CSP policy builder and its configuration validation."""
import pytest

from app.core.config import Settings
from app.core.csp import build_csp_policy, validate_csp_origins


def test_default_policy_is_restrictive() -> None:
    policy = build_csp_policy(connect_origins="", production=False)
    assert "default-src 'self'" in policy
    assert "base-uri 'self'" in policy
    assert "frame-ancestors 'self'" in policy
    assert "form-action 'self'" in policy
    assert "object-src 'none'" in policy
    assert "frame-src 'none'" in policy
    assert "connect-src" not in policy
    assert "upgrade-insecure-requests" not in policy


def test_production_policy_upgrades_insecure_requests() -> None:
    policy = build_csp_policy(connect_origins="", production=True)
    assert "upgrade-insecure-requests" in policy


def test_connect_origins_widen_connect_src_only() -> None:
    policy = build_csp_policy(
        connect_origins="https://supabase.example.com,wss://n8n.example.com:5678",
        production=False,
    )
    assert (
        "connect-src 'self' https://supabase.example.com wss://n8n.example.com:5678"
        in policy
    )
    assert "default-src 'self'" in policy


def test_blank_origins_parse_to_empty() -> None:
    assert validate_csp_origins("") == []
    assert validate_csp_origins("  , , ") == []


def test_valid_origins_are_trimmed() -> None:
    assert validate_csp_origins(" https://a.example.com , http://b.example.com:8080 ") == [
        "https://a.example.com",
        "http://b.example.com:8080",
    ]


@pytest.mark.parametrize(
    "origin",
    [
        "javascript:alert(1)",
        "https://*.example.com",
        "'unsafe-inline'",
        "https://example.com/path with space",
        "//example.com",
        "https://",
        "*",
    ],
)
def test_invalid_origins_are_rejected(origin: str) -> None:
    with pytest.raises(ValueError):
        validate_csp_origins(origin)


def test_build_policy_rejects_invalid_origins() -> None:
    with pytest.raises(ValueError):
        build_csp_policy(connect_origins="https://*.example.com", production=False)


def test_validate_runtime_rejects_invalid_csp_origins() -> None:
    settings = Settings(CSP_CONNECT_ORIGINS="javascript:alert(1)")
    with pytest.raises(RuntimeError, match="CSP configuration error"):
        settings.validate_runtime()


def test_validate_runtime_accepts_valid_csp_origins() -> None:
    settings = Settings(CSP_CONNECT_ORIGINS="https://supabase.example.com")
    settings.validate_runtime()


def test_production_validation_requires_csp() -> None:
    settings = Settings(
        APP_ENV="production",
        APP_DEBUG=False,
        SECRET_KEY="overridden-secret",
        DATABASE_URL="postgresql+asyncpg://user:pass@db:5432/agencyos",
        ENABLE_CSP=False,
    )
    with pytest.raises(RuntimeError, match="ENABLE_CSP must be enabled in production"):
        settings.validate_for_production()
