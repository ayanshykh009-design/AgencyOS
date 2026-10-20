"""Regression tests: refresh token is accepted only via the HttpOnly cookie.

V5 Option B removes the deprecated request-body refresh-token path. These
tests prove that a body-only refresh token is rejected even when its value
would otherwise be valid, and that the cookie path is the only accepted one.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.main import create_app


def test_refresh_without_cookie_is_rejected() -> None:
    app = create_app()

    async def _stub_db():
        yield None

    app.dependency_overrides[get_db] = _stub_db
    client = TestClient(app, raise_server_exceptions=False, headers={"Host": "localhost", "Origin": "http://localhost:3000"})
    res = client.post("/api/v1/auth/refresh", json={"refresh_token": "would-be-valid"})
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "auth.invalid_refresh"


def test_refresh_with_cookie_reaches_service() -> None:
    app = create_app()

    async def _stub_db():
        yield None

    app.dependency_overrides[get_db] = _stub_db
    client = TestClient(app, raise_server_exceptions=False, headers={"Host": "localhost", "Origin": "http://localhost:3000"})
    client.cookies.set("agencyos.refresh", "cookie-token")
    res = client.post("/api/v1/auth/refresh")
    # The stubbed DB yields None, so the service raises; the point is the
    # request was not rejected as missing-token (401 invalid_refresh) merely
    # because no body was supplied. Any non-401-invalid_refresh status shows
    # the cookie path was taken.
    code = res.json().get("error", {}).get("code")
    assert res.status_code != 401 or code != "auth.invalid_refresh"
