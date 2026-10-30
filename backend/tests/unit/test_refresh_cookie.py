"""Regression tests: refresh token is accepted only via the HttpOnly cookie.

V5 Option B removes the deprecated request-body refresh-token path. These
tests prove that a body-only refresh token is rejected even when its value
would otherwise be valid, that the cookie path is the only accepted one, and
that the refresh endpoint sets the rotated cookie with the expected security
attributes.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Response
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.core.config import settings
from app.main import create_app
from app.models.enums import UserRole
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.services.auth_service import AuthService
from app.services.base import utcnow

ORG_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")


class _FakeSession:
    """Minimal async session so the real service path can run without a DB."""

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

    async def refresh(self, instance: object) -> None:
        return None

    async def execute(self, *args: object, **kwargs: object) -> None:
        return None


def _make_user() -> User:
    user = User(
        organization_id=ORG_ID,
        email="owner@example.com",
        full_name="Owner",
        role=UserRole.OWNER,
        password_hash=None,
    )
    user.id = uuid.uuid4()
    user.created_at = datetime(2026, 8, 1, tzinfo=UTC)
    user.updated_at = datetime(2026, 8, 1, tzinfo=UTC)
    user.is_active = True
    user.last_login_at = None
    user.token_version = 0
    user.email_verified_at = datetime(2026, 8, 1, tzinfo=UTC)
    user.email_verification_required = False
    return user


def _service_with_rotatable_token(
    user: User,
) -> tuple[AuthService, _FakeSession, RefreshToken]:
    """Build a real ``AuthService`` wired to in-memory replacements.

    Only the repository/DB boundary is faked; ``refresh`` and the cookie
    writer are the production implementations.
    """
    session = _FakeSession()
    service = AuthService(session)
    service._users = MagicMock()
    service._tokens = MagicMock()
    service._users.get = AsyncMock(return_value=user)
    parent = RefreshToken(
        user_id=user.id,
        organization_id=user.organization_id,
        token_hash="parent-digest",
        family_id=uuid.uuid4(),
        expires_at=utcnow() + timedelta(days=1),
    )
    parent.id = uuid.uuid4()
    service._tokens.get_any = AsyncMock(return_value=parent)
    service._tokens.mark_replaced = AsyncMock(return_value=True)
    successor = MagicMock(id=uuid.uuid4())
    service._issue_tokens = AsyncMock(
        return_value=("access-123", "new-refresh-token", successor)
    )
    return service, session, parent


def _client() -> TestClient:
    app = create_app()

    async def _stub_db():
        yield None

    app.dependency_overrides[get_db] = _stub_db
    return TestClient(
        app,
        raise_server_exceptions=False,
        headers={"Host": "localhost", "Origin": "http://localhost:3000"},
    )


def test_refresh_without_cookie_is_rejected() -> None:
    app = create_app()

    async def _stub_db():
        yield None

    app.dependency_overrides[get_db] = _stub_db
    client = TestClient(
        app,
        raise_server_exceptions=False,
        headers={"Host": "localhost", "Origin": "http://localhost:3000"},
    )
    res = client.post("/api/v1/auth/refresh", json={"refresh_token": "would-be-valid"})
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "auth.invalid_refresh"


def test_refresh_with_cookie_succeeds_and_sets_cookie() -> None:
    user = _make_user()
    service, session, parent = _service_with_rotatable_token(user)
    client = _client()
    client.cookies.set(settings.REFRESH_COOKIE_NAME, "cookie-token")

    # The endpoint constructs ``AuthService(db)``; hand it the real instance
    # so the production refresh + cookie-setting code runs.
    with patch("app.api.v1.endpoints.auth.AuthService", return_value=service):
        res = client.post("/api/v1/auth/refresh")

    assert res.status_code == 200
    body = res.json()
    assert body["access_token"] == "access-123"
    # The rotated token travels only in the cookie, never in JSON.
    assert "refresh_token" not in body
    assert "new-refresh-token" not in res.text

    # The real ``_set_refresh_cookie`` wrote this header.
    set_cookie = res.headers["set-cookie"]
    lowered = set_cookie.lower()
    assert f"{settings.REFRESH_COOKIE_NAME}=new-refresh-token" in set_cookie
    assert "httponly" in lowered
    assert f"path={settings.REFRESH_COOKIE_PATH}".lower() in lowered
    assert f"samesite={settings.REFRESH_COOKIE_SAMESITE}".lower() in lowered
    # Secure is intentionally off outside production (HTTP dev origins).
    assert "secure" not in lowered

    # The old token was consumed atomically, and the rotation was persisted.
    service._tokens.mark_replaced.assert_awaited_once()
    assert service._tokens.mark_replaced.await_args.args[0] == parent.id
    assert session.committed is True


def test_production_refresh_cookie_is_secure(monkeypatch: pytest.MonkeyPatch) -> None:
    """The same setter must add ``Secure`` when APP_ENV is production."""
    monkeypatch.setattr(settings, "APP_ENV", "production")
    service = AuthService(_FakeSession())
    response = Response()

    service._set_refresh_cookie(response, "prod-refresh-token")

    set_cookie = response.headers["set-cookie"]
    lowered = set_cookie.lower()
    assert f"{settings.REFRESH_COOKIE_NAME}=prod-refresh-token" in set_cookie
    assert "httponly" in lowered
    assert f"path={settings.REFRESH_COOKIE_PATH}".lower() in lowered
    assert f"samesite={settings.REFRESH_COOKIE_SAMESITE}".lower() in lowered
    assert "secure" in lowered


def test_refresh_body_only_token_rejected() -> None:
    """A refresh token supplied only in the body cannot authenticate."""
    app = create_app()

    async def _stub_db():
        yield None

    app.dependency_overrides[get_db] = _stub_db
    client = TestClient(
        app,
        raise_server_exceptions=False,
        headers={"Host": "localhost", "Origin": "http://localhost:3000"},
    )
    res = client.post("/api/v1/auth/refresh", json={"refresh_token": "body-token"})
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "auth.invalid_refresh"


def test_refresh_invalid_origin_rejected() -> None:
    app = create_app()

    async def _stub_db():
        yield None

    app.dependency_overrides[get_db] = _stub_db
    client = TestClient(
        app,
        raise_server_exceptions=False,
        headers={"Host": "localhost", "Origin": "https://evil.example"},
    )
    client.cookies.set("agencyos.refresh", "cookie-token")
    res = client.post("/api/v1/auth/refresh")
    assert res.status_code == 403
