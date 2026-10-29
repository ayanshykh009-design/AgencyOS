"""Runtime regression tests: rate-limited routes must not 500 on success (R7).

slowapi is configured with ``headers_enabled=True``, so after a handler returns
it injects ``X-RateLimit-*``/``Retry-After`` into the endpoint's ``response``
argument. A handler decorated with ``@limiter.limit(...)`` that does not declare
``response: Response`` therefore raises *after* the successful work and the
client sees HTTP 500.

These tests drive the real FastAPI application and the real SlowAPI wrapper
(the decorators are never bypassed). Only the database session and the service
layer are replaced, because their behaviour is covered by the unit/integration
suites. Every affected handler in ``ai.py``, ``agents.py`` and ``teams.py`` is
exercised through its successful path, and its rate-limit headers are asserted
so a missing ``response`` parameter regresses loudly.
"""

from __future__ import annotations

import uuid
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_db
from app.core.config import settings
from app.core.rate_limit import limiter
from app.main import app
from app.models.agent_run import AgentRun
from app.models.enums import (
    AgentRunStatus,
    AgentRunTrigger,
    InviteStatus,
    UserRole,
)
from app.models.team_invite import TeamInvite

ORG_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
LEAD_ID = uuid.uuid4()
RUN_ID = uuid.uuid4()
INVITE_TOKEN = "t" * 32
STRICT_LIMIT = 20  # @limiter.limit(settings.RATE_LIMIT_STRICT) at import time

RATE_LIMIT_HEADERS = ("x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-reset")


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
    """Real app, stubbed DB session (services are patched per test)."""

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


def _agent_run() -> AgentRun:
    now = datetime.now(UTC)
    return AgentRun(
        id=RUN_ID,
        organization_id=ORG_ID,
        agent_name="founder_assistant",
        status=AgentRunStatus.QUEUED,
        trigger=AgentRunTrigger.MANUAL,
        workflow_id=None,
        input={},
        output=None,
        error=None,
        duration_ms=None,
        cost=Decimal("0"),
        started_at=None,
        finished_at=None,
        cancel_requested_at=None,
        cancelled_by_user_id=None,
        idempotency_key=None,
        trace_id=None,
        created_at=now,
        updated_at=now,
    )


def _team_invite() -> TeamInvite:
    now = datetime.now(UTC)
    return TeamInvite(
        id=uuid.uuid4(),
        organization_id=ORG_ID,
        email="invitee@example.com",
        full_name="Invitee",
        role=UserRole.MEMBER,
        token_hash="0" * 64,
        invited_by_user_id=USER_ID,
        status=InviteStatus.PENDING,
        expires_at=now + timedelta(days=7),
        accepted_at=None,
        accepted_user_id=None,
        revoked_at=None,
        created_at=now,
        updated_at=now,
    )


# --- ai.py (5 limited handlers) -------------------------------------------


def test_ai_get_settings_success(api_client: TestClient) -> None:
    fake = MagicMock()
    fake.get_ai_settings = AsyncMock(return_value=("anthropic", "claude-sonnet", False, False))

    with _authenticated():
        with patch("app.api.v1.endpoints.ai.AIService", return_value=fake):
            res = api_client.get("/api/v1/ai/settings")

    assert res.status_code == 200, res.text
    assert res.json()["provider"] == "anthropic"
    _assert_rate_limit_headers(res)


def test_ai_update_settings_success(api_client: TestClient) -> None:
    fake = MagicMock()
    fake.update_ai_settings = AsyncMock()
    fake.get_ai_settings = AsyncMock(return_value=("openai", "gpt-5", True, True))

    with _authenticated():
        with patch("app.api.v1.endpoints.ai.AIService", return_value=fake):
            res = api_client.patch("/api/v1/ai/settings", json={"kill_switch": True})

    assert res.status_code == 200, res.text
    assert res.json()["kill_switch"] is True
    _assert_rate_limit_headers(res)


def test_ai_list_tools_success(api_client: TestClient) -> None:
    fake = MagicMock()
    fake.tools = AsyncMock(
        return_value=[
            {"name": "search_leads", "description": "Search leads", "parameters": {"q": "str"}}
        ]
    )

    with _authenticated():
        with patch("app.api.v1.endpoints.ai.AIService", return_value=fake):
            res = api_client.get("/api/v1/ai/tools")

    assert res.status_code == 200, res.text
    assert res.json()[0]["name"] == "search_leads"
    _assert_rate_limit_headers(res)


def test_ai_run_brain_success(api_client: TestClient) -> None:
    fake = MagicMock()
    fake.assert_ai_enabled = AsyncMock()
    fake.agent_for_goal = MagicMock(return_value="founder_assistant")
    fake_agents = MagicMock()
    fake_agents.create_run = AsyncMock(return_value=_agent_run())

    with _authenticated():
        with (
            patch("app.api.v1.endpoints.ai.AIService", return_value=fake),
            patch("app.api.v1.endpoints.ai.AgentService", return_value=fake_agents),
        ):
            res = api_client.post(
                "/api/v1/ai/run",
                json={"goal": "draft_email", "lead_id": str(LEAD_ID)},
            )

    assert res.status_code == 201, res.text
    assert res.json()["agent_name"] == "founder_assistant"
    _assert_rate_limit_headers(res)


def test_ai_dispatch_success(api_client: TestClient) -> None:
    fake = MagicMock()
    fake.dispatch = AsyncMock(return_value={"ok": True})

    with _authenticated():
        with patch("app.api.v1.endpoints.ai.AIService", return_value=fake):
            res = api_client.post(
                "/api/v1/ai/dispatch",
                json={"workflow": "outreach-dispatch", "payload": {"msg": "hi"}},
            )

    assert res.status_code == 200, res.text
    assert res.json()["data"] == {"ok": True}
    _assert_rate_limit_headers(res)


# --- agents.py (2 limited handlers) ---------------------------------------


def test_agents_create_run_success(api_client: TestClient) -> None:
    fake = MagicMock()
    fake.create_run = AsyncMock(return_value=_agent_run())

    with _authenticated():
        with patch("app.api.v1.endpoints.agents.AgentService", return_value=fake):
            res = api_client.post(
                "/api/v1/agents/runs",
                json={
                    "organization_id": str(ORG_ID),
                    "agent_name": "founder_assistant",
                },
            )

    assert res.status_code == 201, res.text
    assert res.json()["status"] == AgentRunStatus.QUEUED.value
    _assert_rate_limit_headers(res)


def test_agents_cancel_run_success(api_client: TestClient) -> None:
    fake = MagicMock()
    fake.cancel_run = AsyncMock(return_value=_agent_run())

    with _authenticated():
        with patch("app.api.v1.endpoints.agents.AgentService", return_value=fake):
            res = api_client.post(f"/api/v1/agents/runs/{RUN_ID}/cancel")

    assert res.status_code == 200, res.text
    assert res.json()["id"] == str(RUN_ID)
    _assert_rate_limit_headers(res)


# --- teams.py (2 limited handlers) ----------------------------------------


def test_teams_lookup_invite_success(api_client: TestClient) -> None:
    fake = MagicMock()
    fake.lookup_invite = AsyncMock(return_value=_team_invite())
    fake.organization_name = AsyncMock(return_value="Acme Agency")

    with patch("app.api.v1.endpoints.teams.TeamService", return_value=fake):
        res = api_client.get(f"/api/v1/teams/public/{INVITE_TOKEN}")

    assert res.status_code == 200, res.text
    assert res.json()["email"] == "invitee@example.com"
    assert res.json()["organization_name"] == "Acme Agency"
    _assert_rate_limit_headers(res)


def test_teams_accept_invite_success(api_client: TestClient) -> None:
    fake = MagicMock()
    fake.accept_invite = AsyncMock(return_value=_team_invite())

    with patch("app.api.v1.endpoints.teams.TeamService", return_value=fake):
        res = api_client.post(
            "/api/v1/teams/accept",
            json={
                "token": INVITE_TOKEN,
                "full_name": "New Person",
                "password": "correct-horse-battery",
            },
        )

    assert res.status_code == 200, res.text
    assert res.json()["email"] == "invitee@example.com"
    _assert_rate_limit_headers(res)


# --- authn/authz and limiter still enforced -------------------------------


def test_limited_ai_route_still_requires_auth(api_client: TestClient) -> None:
    res = api_client.get("/api/v1/ai/tools")

    assert res.status_code == 401
    assert res.json()["error"]["code"] == "auth.missing_token"


def test_limited_agent_route_still_requires_permission(api_client: TestClient) -> None:
    with _authenticated(role=UserRole.VIEWER):
        res = api_client.post(
            "/api/v1/agents/runs",
            json={"organization_id": str(ORG_ID), "agent_name": "founder_assistant"},
        )

    assert res.status_code == 403


def test_teams_lookup_rate_limit_still_rejects(api_client: TestClient) -> None:
    fake = MagicMock()
    fake.lookup_invite = AsyncMock(return_value=_team_invite())
    fake.organization_name = AsyncMock(return_value="Acme Agency")

    with patch("app.api.v1.endpoints.teams.TeamService", return_value=fake):
        statuses = [
            api_client.get(f"/api/v1/teams/public/{INVITE_TOKEN}").status_code
            for _ in range(STRICT_LIMIT + 1)
        ]
        blocked = api_client.get(f"/api/v1/teams/public/{INVITE_TOKEN}")

    assert statuses[:STRICT_LIMIT] == [200] * STRICT_LIMIT, statuses
    assert statuses[STRICT_LIMIT] == 429, statuses
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limited"
    assert "retry-after" in {key.lower() for key in blocked.headers}


def test_limited_ai_route_rate_limit_still_rejects(api_client: TestClient) -> None:
    """Covers the ``RATE_LIMIT_DEFAULT`` group (200/min) used by ai settings."""
    fake = MagicMock()
    fake.get_ai_settings = AsyncMock(return_value=("anthropic", "claude-sonnet", False, False))
    default_limit = int(settings.RATE_LIMIT_DEFAULT.split("/", 1)[0])

    with _authenticated():
        with patch("app.api.v1.endpoints.ai.AIService", return_value=fake):
            statuses = [
                api_client.get("/api/v1/ai/settings").status_code
                for _ in range(default_limit + 1)
            ]

    assert statuses[:default_limit] == [200] * default_limit
    assert statuses[default_limit] == 429
