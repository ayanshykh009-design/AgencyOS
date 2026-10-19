"""Prove the auth rate limiter actually enforces, not just that it is configured.

A `@limiter.limit(...)` decorator does nothing unless the limiter is registered
on the application (`app.state.limiter`) *and* a `RateLimitExceeded` handler is
installed. These tests exercise the real HTTP path and assert a real 429.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from app.core.rate_limit import limiter, register_rate_limit
from app.main import create_app

# The decorator captures settings.RATE_LIMIT_STRICT at import time, so the real
# auth routes are limited at 20/minute; one request past that must be rejected.
_STRICT_LIMIT = 20


def test_limiter_429_includes_retry_after() -> None:
    """The IP-level limiter path must send Retry-After so clients can back off."""
    _reset_counters()
    app = FastAPI()
    register_rate_limit(app)

    @app.post("/probe2")
    @limiter.limit("1/minute")
    async def probe2(request: Request, response: Response) -> dict[str, bool]:
        return {"ok": True}

    client = TestClient(app)
    assert client.post("/probe2").status_code == 200
    blocked = client.post("/probe2")
    assert blocked.status_code == 429
    assert "retry-after" in {k.lower() for k in blocked.headers}


def _reset_counters() -> None:
    """Isolate tests from each other (the limiter is a module-level singleton)."""
    storage = getattr(limiter, "_storage", None)
    reset = getattr(storage, "reset", None)
    if callable(reset):
        reset()


def test_register_rate_limit_wires_state_and_handler() -> None:
    app = FastAPI()
    register_rate_limit(app)
    assert app.state.limiter is limiter
    from slowapi.errors import RateLimitExceeded

    assert RateLimitExceeded in app.exception_handlers


def test_create_app_registers_the_limiter() -> None:
    """The real application - not a stub - must carry the limiter."""
    from slowapi.errors import RateLimitExceeded

    app = create_app()
    assert getattr(app.state, "limiter", None) is limiter
    assert RateLimitExceeded in app.exception_handlers


def test_decorated_route_returns_429_with_retry_after() -> None:
    _reset_counters()
    app = FastAPI()
    register_rate_limit(app)

    @app.post("/probe")
    @limiter.limit("3/minute")
    async def probe(request: Request, response: Response) -> dict[str, bool]:
        return {"ok": True}

    client = TestClient(app)
    statuses = [client.post("/probe").status_code for _ in range(5)]

    assert statuses[:3] == [200, 200, 200], statuses
    assert statuses[3] == 429, statuses
    assert statuses[4] == 429, statuses
    blocked = client.post("/probe")
    assert blocked.status_code == 429
    body = blocked.json()
    assert body["error"]["code"] == "rate_limited"
    # The 429 body must not echo credentials or internal detail.
    assert "password" not in blocked.text.lower()


def test_real_login_route_is_rate_limited() -> None:
    """End-to-end proof against the real application, not a stub.

    A configuration value does not prove a route is protected, so this drives
    POST /api/v1/auth/login past the strict limit and requires a real 429 with
    the standard error envelope. The DB session is a MagicMock: the point is the
    limiter, not credential checking, and no real password is ever used.
    """
    _reset_counters()
    from unittest.mock import MagicMock

    from app.api.deps import get_db

    app = create_app()

    async def _stub_db():
        yield MagicMock()

    app.dependency_overrides[get_db] = _stub_db
    # TrustedHostMiddleware rejects the default "testserver" Host.
    client = TestClient(app, raise_server_exceptions=False, headers={"Host": "localhost"})

    payload = {"email": "probe@example.com", "password": "not-a-real-password"}
    url = "/api/v1/auth/login"
    statuses = [client.post(url, json=payload).status_code for _ in range(_STRICT_LIMIT + 3)]

    assert 429 in statuses, f"login route never rate limited: {statuses}"
    # Requests inside the budget must NOT be throttled.
    assert all(code != 429 for code in statuses[:_STRICT_LIMIT]), statuses
    # Everything past the budget is throttled.
    assert all(code == 429 for code in statuses[_STRICT_LIMIT:]), statuses

    blocked = client.post(url, json=payload)
    assert blocked.status_code == 429
    body = blocked.json()
    assert body["error"]["code"] == "rate_limited"
    # Rule 12: the throttle response must not echo credentials or internals.
    assert "password" not in blocked.text.lower()
    assert "not-a-real-password" not in blocked.text


def test_production_requires_shared_limiter_storage() -> None:
    """memory:// counters are per-process and dilute throttling across replicas."""
    from app.core.config import Settings

    base = dict(
        APP_ENV="production",
        APP_DEBUG=False,
        SECRET_KEY="z" * 32,
        DATABASE_URL="postgresql://agencyos:secret@db:5432/agencyos",
        WORKER_DATABASE_URL="postgresql://agencyos:secret@db:5432/agencyos",
        ENABLE_CSP=True,
        CREDENTIALS_ENC_KEY="c2VjcmV0LW1hc3Rlci1rZXktZm9yLXRlc3Rpbmctb25seQ==",
        EMAIL_VERIFICATION_ENABLED=True,
        MFA_ENABLED=True,
        SMTP_HOST="smtp.example.com",
        SMTP_FROM_EMAIL="no-reply@example.com",
    )
    with pytest.raises(RuntimeError, match="REDIS_URL"):
        Settings(**base, REDIS_URL="").validate_for_production()
    assert Settings(**base, REDIS_URL="redis://cache:6379/0").validate_for_production() is None
