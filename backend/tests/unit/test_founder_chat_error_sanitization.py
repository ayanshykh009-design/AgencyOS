"""Founder chat must never persist or return raw provider/SDK error text."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.agents.executors.base import ExecutorResult
from app.models.founder_conversation import FounderConversation
from app.models.founder_message import FounderMessage
from app.services import founder_chat_service as mod

ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
_SECRET = "sk-secret-abcdef"
_HOST = "https://provider.internal.example"
_BODY = '{"api_key":"leaked"}'


class _FakeSession:
    def __init__(self) -> None:
        self.flushes = 0

    async def flush(self) -> None:
        self.flushes += 1


async def test_founder_chat_persists_and_returns_only_generic_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    added: list[FounderMessage] = []

    class _MessageRepo:
        def __init__(self, session: Any) -> None:
            pass

        def add(self, message: FounderMessage) -> None:
            added.append(message)

    class _ConversationRepo:
        def __init__(self, session: Any) -> None:
            pass

        def add(self, conversation: FounderConversation) -> None:
            pass

        async def get(self, org_id: uuid.UUID, cid: uuid.UUID) -> FounderConversation | None:
            return None

    class _FailingExecutor:
        async def execute(self, ctx: Any) -> ExecutorResult:
            return ExecutorResult(
                success=False,
                error=f"POST {_HOST} failed with {_BODY} using {_SECRET}",
            )

    async def _commit(session: Any) -> None:
        return None

    monkeypatch.setattr(mod, "FounderMessageRepository", _MessageRepo)
    monkeypatch.setattr(mod, "FounderConversationRepository", _ConversationRepo)
    monkeypatch.setattr(mod, "get_executor", lambda name: _FailingExecutor())
    monkeypatch.setattr(mod, "commit_with_retry", _commit)

    service = mod.FounderChatService(_FakeSession())  # type: ignore[arg-type]
    response = await service.send_message(
        ORG_ID,
        user=type("User", (), {"id": uuid.uuid4()})(),  # type: ignore[arg-type]
        conversation_id=None,
        message="What is our pipeline?",
    )

    generic = "I wasn't able to process that request. Please try again."
    assert response["ok"] is False
    assert response["error"] == generic
    assert response["message"]["body"] == generic

    assert added
    assistant = added[-1]
    assert assistant.metadata_["error"] == generic
    for value in (
        assistant.body,
        str(assistant.metadata_),
        str(response),
    ):
        assert _HOST not in value
        assert _SECRET not in value
        assert _BODY not in value
