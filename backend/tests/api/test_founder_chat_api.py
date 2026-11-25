"""Founder chat API regressions: true pagination totals and AI rate limiting.

The database session and the service/executor layer are stubbed: this exercises
the real router (permissions, SlowAPI decorator, response envelope) without an
LLM call or a database.
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
from app.models.enums import FounderActionType, FounderProposalStatus, UserRole

ORG_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
AI_LIMIT = int(settings.RATE_LIMIT_AI.split("/", 1)[0])


def _reset_counters() -> None:
    storage = getattr(limiter, "_storage", None)
    reset = getattr(storage, "reset", None)
    if callable(reset):
        reset()


@pytest.fixture(autouse=True)
def _isolated_limiter() -> Generator[None, None, None]:
    _reset_counters()
    yield
    _reset_counters()


@pytest.fixture
def api_client() -> Generator[TestClient, None, None]:
    async def _stub_db():
        yield MagicMock()

    app.dependency_overrides[get_db] = _stub_db
    try:
        with TestClient(app, base_url="http://localhost") as client:
            yield client
    finally:
        app.dependency_overrides.clear()


@contextmanager
def _authenticated():
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=USER_ID, organization_id=ORG_ID, role=UserRole.OWNER
    )
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def _conversation() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        title="hello",
        is_archived=False,
        created_at=None,
        last_message_at=None,
    )


def _proposal() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        conversation_id=None,
        action_type=FounderActionType.CREATE_TASK,
        title="Create task: follow up",
        status=FounderProposalStatus.PROPOSED,
        justification=None,
        payload={},
        expires_at=None,
        decided_at=None,
        created_at=None,
    )


def test_conversation_list_reports_true_filtered_total(api_client: TestClient) -> None:
    items = [_conversation()]
    with (
        _authenticated(),
        patch(
            "app.api.v1.endpoints.founder_chat.FounderChatService.list_conversations",
            new_callable=AsyncMock,
            return_value=items,
        ),
        patch(
            "app.api.v1.endpoints.founder_chat.FounderChatRepository.count_conversations",
            new_callable=AsyncMock,
            return_value=11,
        ) as count,
    ):
        res = api_client.get("/api/v1/founder/conversations?limit=1&offset=0")

    assert res.status_code == 200, res.text
    body = res.json()
    assert len(body["items"]) == 1
    assert body["total"] == 11
    count.assert_awaited_once_with(ORG_ID, include_archived=False)


def test_proposal_list_reports_true_filtered_total(api_client: TestClient) -> None:
    items = [_proposal()]
    with (
        _authenticated(),
        patch(
            "app.api.v1.endpoints.founder_chat.FounderActionService.list_proposals",
            new_callable=AsyncMock,
            return_value=items,
        ),
        patch(
            "app.api.v1.endpoints.founder_chat.FounderActionService.count_proposals",
            new_callable=AsyncMock,
            return_value=8,
        ) as count,
    ):
        res = api_client.get("/api/v1/founder/proposals?proposal_status=proposed&limit=1&offset=0")

    assert res.status_code == 200, res.text
    body = res.json()
    assert len(body["items"]) == 1
    assert body["total"] == 8
    count.assert_awaited_once_with(ORG_ID, status=FounderProposalStatus.PROPOSED)


def test_founder_chat_is_rate_limited_with_executor_mocked(api_client: TestClient) -> None:
    reply = {
        "conversation_id": str(uuid.uuid4()),
        "message": {
            "id": str(uuid.uuid4()),
            "sender": "assistant",
            "body": "ok",
            "sent_at": None,
        },
        "proposals": [],
        "intent": {},
        "ok": True,
        "error": None,
    }
    fake = MagicMock()
    fake.send_message = AsyncMock(return_value=reply)

    with (
        _authenticated(),
        patch("app.api.v1.endpoints.founder_chat.FounderChatService", return_value=fake),
    ):
        responses = [
            api_client.post("/api/v1/founder/chat", json={"message": "hello"})
            for _ in range(AI_LIMIT + 1)
        ]

    assert [r.status_code for r in responses] == [200] * AI_LIMIT + [429]
    assert fake.send_message.await_count == AI_LIMIT
    lowered = {k.lower(): v for k, v in responses[0].headers.items()}
    assert lowered["x-ratelimit-limit"] == str(AI_LIMIT)
    assert "x-ratelimit-remaining" in lowered
    blocked = responses[-1]
    assert blocked.json()["error"]["code"] == "rate_limited"
    assert "retry-after" in {k.lower() for k in blocked.headers}
