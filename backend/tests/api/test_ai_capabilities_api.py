"""API tests for the authenticated AI capability endpoint.

The real FastAPI app and SlowAPI rate-limit decorators are exercised; only the
database session, ``AIService.is_ai_enabled``, and deployment flags are
replaced. The limiter is a module-level singleton, so its counters are reset
around every test.
"""

from __future__ import annotations

import uuid
from collections.abc import Generator
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_db
from app.core.config import settings
from app.core.rate_limit import limiter
from app.main import app
from app.models.enums import UserRole

ORG_ID = uuid.uuid4()
USER_ID = uuid.uuid4()

RATE_LIMIT_HEADERS = ("x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-reset")
CAPABILITY_FIELDS = {
    "agent_runtime_enabled",
    "founder_assistant_enabled",
    "intelligence_triage_enabled",
    "intelligence_narrative_enabled",
    "ai_execution_enabled",
    "ai_budget_configured",
}
# The payload must stay boolean-only: no identifiers, endpoints, or credentials.
SUSPICIOUS_KEY_FRAGMENTS = ("key", "secret", "host", "token", "url", "org", "model", "provider")


def _reset_counters() -> None:
    """The limiter is a module-level singleton; isolate each test."""
    reset = getattr(limiter, "reset", None)
    if callable(reset):
        reset()
        return
    storage = getattr(limiter, "_storage", None)
    storage_reset = getattr(storage, "reset", None)
    if callable(storage_reset):
        storage_reset()


@pytest.fixture(autouse=True)
def _isolated_limiter() -> Generator[None, None, None]:
    _reset_counters()
    yield
    _reset_counters()


@pytest.fixture
def api_client() -> Generator[TestClient, None, None]:
    """Real app, stubbed DB session (the service method is patched per test)."""

    async def _stub_db():
        yield MagicMock()

    app.dependency_overrides[get_db] = _stub_db
    try:
        with TestClient(app, base_url="http://localhost") as client:
            yield client
    finally:
        app.dependency_overrides.clear()


@contextmanager
def _authenticated(role: UserRole = UserRole.OWNER):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=USER_ID, organization_id=ORG_ID, role=role
    )
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def _assert_rate_limit_headers(res) -> None:
    lowered = {key.lower(): value for key, value in res.headers.items()}
    for header in RATE_LIMIT_HEADERS:
        assert header in lowered, f"missing {header}: {sorted(lowered)}"
    assert lowered["x-ratelimit-limit"].isdigit()


def test_capabilities_requires_auth(api_client: TestClient) -> None:
    res = api_client.get("/api/v1/ai/capabilities")

    assert res.status_code == 401
    assert res.json()["error"]["code"] == "auth.missing_token"


def test_capabilities_returns_all_booleans_without_secrets(api_client: TestClient) -> None:
    """All six flags map to their source and no secret-like field is exposed."""
    with (
        patch(
            "app.services.ai_service.AIService.is_ai_enabled",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_is_enabled,
        patch.object(settings, "AGENT_RUNTIME_ENABLED", True),
        patch.object(settings, "FOUNDER_ASSISTANT_ENABLED", False),
        patch.object(settings, "INTELLIGENCE_TRIAGE_ENABLED", True),
        patch.object(settings, "INTELLIGENCE_NARRATIVE_ENABLED", False),
        patch.object(settings, "AI_ORG_DAILY_TOKEN_BUDGET", 100_000),
        patch.object(settings, "AI_ORG_DAILY_COST_BUDGET_USD", 0.0),
    ):
        with _authenticated():
            res = api_client.get("/api/v1/ai/capabilities")

    assert res.status_code == 200, res.text
    assert res.json() == {
        "agent_runtime_enabled": True,
        "founder_assistant_enabled": False,
        "intelligence_triage_enabled": True,
        "intelligence_narrative_enabled": False,
        "ai_execution_enabled": True,
        "ai_budget_configured": True,
    }
    # Organization is derived from CurrentUser, never accepted from the client.
    mock_is_enabled.assert_awaited_once_with(ORG_ID)

    payload = res.json()
    assert set(payload) == CAPABILITY_FIELDS
    assert all(isinstance(value, bool) for value in payload.values())
    assert not [
        field
        for field in payload
        if any(part in field.lower() for part in SUSPICIOUS_KEY_FRAGMENTS)
    ]
    _assert_rate_limit_headers(res)


def test_capabilities_fail_closed_flags_are_false(api_client: TestClient) -> None:
    """A denied org and unconfigured budgets report false, with rate-limit headers."""
    with (
        patch(
            "app.services.ai_service.AIService.is_ai_enabled",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch.object(settings, "AGENT_RUNTIME_ENABLED", False),
        patch.object(settings, "FOUNDER_ASSISTANT_ENABLED", False),
        patch.object(settings, "INTELLIGENCE_TRIAGE_ENABLED", False),
        patch.object(settings, "INTELLIGENCE_NARRATIVE_ENABLED", False),
        patch.object(settings, "AI_ORG_DAILY_TOKEN_BUDGET", 0),
        patch.object(settings, "AI_ORG_DAILY_COST_BUDGET_USD", 0.0),
    ):
        with _authenticated(role=UserRole.VIEWER):
            res = api_client.get("/api/v1/ai/capabilities")

    assert res.status_code == 200, res.text
    assert set(res.json()) == CAPABILITY_FIELDS
    assert not any(res.json().values())
    _assert_rate_limit_headers(res)
