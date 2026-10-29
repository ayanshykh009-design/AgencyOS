"""API contract tests for the pre-authentication verification-resend endpoint.

``POST /api/v1/auth/verify-email/resend`` is unauthenticated and always returns
``202`` so unverified users can recover from the login verification gate. These
tests drive the real router + rate limiter and assert both the enumeration-safe
response shape and the underlying token/email side effects.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.core.config import settings
from app.core.rate_limit import limiter
from app.main import create_app
from app.models.enums import UserRole
from app.models.user import User
from app.services.account_security_service import AccountSecurityService
from app.services.base import utcnow

RESEND_URL = "/api/v1/auth/verify-email/resend"
STRICT_LIMIT = 20  # @limiter.limit(settings.RATE_LIMIT_STRICT) at import time
EXPECTED_DETAIL = "Verification email sent"


@pytest.fixture(autouse=True)
def _email_verification_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Most tests exercise the enabled path; the disabled case overrides this."""
    monkeypatch.setattr(settings, "EMAIL_VERIFICATION_ENABLED", True)


def _reset_counters() -> None:
    """Isolate tests from each other (the limiter is a module-level singleton)."""
    storage = getattr(limiter, "_storage", None)
    reset = getattr(storage, "reset", None)
    if callable(reset):
        reset()


class _SessionStub:
    """Async session boundary so the real service can run without a database."""

    def __init__(self) -> None:
        self.added: list[object] = []
        self.committed = False

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        return None

    async def execute(self, *args: object, **kwargs: object) -> None:
        return None


def _make_user(**overrides: object) -> User:
    user = User(
        organization_id=uuid.uuid4(),
        email="owner@example.com",
        full_name="Owner",
        role=UserRole.OWNER,
        password_hash=None,
    )
    user.id = uuid.uuid4()
    user.created_at = utcnow()
    user.updated_at = utcnow()
    user.is_active = True
    user.email_verified_at = None
    user.email_verification_required = True
    for key, value in overrides.items():
        setattr(user, key, value)
    return user


def _client() -> TestClient:
    app = create_app()

    async def _stub_db():
        yield MagicMock()

    app.dependency_overrides[get_db] = _stub_db
    return TestClient(
        app,
        raise_server_exceptions=False,
        headers={"Host": "localhost"},
    )


def _service_for(user: User | None) -> AccountSecurityService:
    """Real service wired to in-memory repository replacements."""
    service = AccountSecurityService(_SessionStub())
    service._users = MagicMock()
    service._users.get_active_by_email = AsyncMock(return_value=user)
    service._tokens = MagicMock()
    service._tokens.invalidate_outstanding = AsyncMock()
    service.send_verification_email = AsyncMock()
    return service


def test_resend_response_is_identical_for_unknown_and_verified_accounts() -> None:
    _reset_counters()
    client = _client()
    payload = {"email": "owner@example.com"}
    unknown_service = _service_for(None)
    verified_service = _service_for(_make_user(email_verified_at=utcnow()))

    with patch(
        "app.api.v1.endpoints.auth.AccountSecurityService",
        return_value=unknown_service,
    ):
        unknown = client.post(RESEND_URL, json=payload)
    with patch(
        "app.api.v1.endpoints.auth.AccountSecurityService",
        return_value=verified_service,
    ):
        verified = client.post(RESEND_URL, json=payload)

    assert unknown.status_code == 202
    assert verified.status_code == 202
    # Byte-identical bodies: the caller cannot distinguish account state.
    assert unknown.json() == verified.json() == {
        "detail": EXPECTED_DETAIL,
        "dev_url": None,
    }
    for service in (unknown_service, verified_service):
        service._tokens.add.assert_not_called()
        service._tokens.invalidate_outstanding.assert_not_awaited()
        service.send_verification_email.assert_not_awaited()


def test_resend_eligible_account_returns_dev_link_and_issues_token() -> None:
    _reset_counters()
    client = _client()
    service = _service_for(_make_user())

    with patch("app.api.v1.endpoints.auth.AccountSecurityService", return_value=service):
        res = client.post(RESEND_URL, json={"email": "owner@example.com"})

    assert res.status_code == 202
    body = res.json()
    assert body["detail"] == EXPECTED_DETAIL
    assert body["dev_url"] is not None
    assert "/verify-email?token=" in body["dev_url"]
    assert service._tokens.add.call_count == 1
    service.send_verification_email.assert_awaited_once()


def test_resend_disabled_flag_is_safe_and_does_not_touch_accounts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_counters()
    monkeypatch.setattr(settings, "EMAIL_VERIFICATION_ENABLED", False)
    client = _client()

    with patch("app.api.v1.endpoints.auth.AccountSecurityService") as service_cls:
        res = client.post(RESEND_URL, json={"email": "owner@example.com"})

    assert res.status_code == 202
    assert res.json() == {
        "detail": "Email verification is not enabled",
        "dev_url": None,
    }
    service_cls.assert_not_called()


def test_resend_production_never_returns_dev_link_or_raw_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_counters()
    monkeypatch.setattr(settings, "APP_ENV", "production")
    client = _client()
    service = _service_for(_make_user())

    with patch("app.api.v1.endpoints.auth.AccountSecurityService", return_value=service):
        res = client.post(RESEND_URL, json={"email": "owner@example.com"})

    assert res.status_code == 202
    body = res.json()
    assert body["dev_url"] is None
    assert "token" not in res.text.lower()
    # The token is still generated and emailed; only the API leak is closed.
    assert service._tokens.add.call_count == 1
    service.send_verification_email.assert_awaited_once()


def test_resend_rejects_invalid_email() -> None:
    _reset_counters()
    client = _client()

    res = client.post(RESEND_URL, json={"email": "not-an-email"})

    assert res.status_code == 422


def test_every_rate_limited_auth_route_accepts_a_response_parameter() -> None:
    """slowapi injects rate-limit headers into the endpoint's ``response`` arg.

    A ``@limiter.limit`` route that does not declare ``response: Response``
    raises on every *successful* call (slowapi cannot find the header target),
    producing a 500. Guard the whole auth router against that regression.
    """
    import inspect

    from app.api.v1.endpoints import auth as auth_module

    offenders = []
    for name, handler in vars(auth_module).items():
        if not inspect.isfunction(handler) or not hasattr(handler, "__wrapped__"):
            continue
        params = inspect.signature(handler).parameters
        if "request" in params and "response" not in params:
            offenders.append(name)

    assert offenders == []


def test_resend_is_rate_limited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_counters()
    monkeypatch.setattr(settings, "EMAIL_VERIFICATION_ENABLED", False)
    client = _client()
    payload = {"email": "owner@example.com"}
    try:
        statuses = [
            client.post(RESEND_URL, json=payload).status_code
            for _ in range(STRICT_LIMIT + 1)
        ]

        assert statuses[:STRICT_LIMIT] == [202] * STRICT_LIMIT, statuses
        assert statuses[STRICT_LIMIT] == 429, statuses

        blocked = client.post(RESEND_URL, json=payload)
        assert blocked.status_code == 429
        assert blocked.json()["error"]["code"] == "rate_limited"
        assert "retry-after" in {key.lower() for key in blocked.headers}
        # The throttle response must not echo the submitted address.
        assert "owner@example.com" not in blocked.text
    finally:
        _reset_counters()
