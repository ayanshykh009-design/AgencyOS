"""Integration tests for the M4 memory-context wiring (prompt + brain + service).

Verifies that ``memory_context`` flows end-to-end into the system prompt while
remaining fully backward compatible (``None`` == unchanged prompt) and that the
AI service gates and fails open.
"""
from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.ai.brain import Brain
from app.ai.context_builder import build_system_prompt
from app.core.config import settings
from app.llm.models import ChatResult, LLMMessage, LLMUsage, MessageRole
from app.llm.providers import ProviderClient
from app.llm.service import LLMService
from app.models.lead import Lead
from app.services.ai_service import AIService
from app.tools.registry import ToolRegistry

ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
MEMORY_BLOCK = "[crm] Pricing concerns\nLead pushed back on annual pricing."


def _lead() -> Lead:
    lead = Lead(
        organization_id=ORG_ID,
        first_name="Ada",
        last_name="Lovelace",
        company="Analytical",
        position="Engineer",
        email="ada@example.com",
    )
    lead.id = uuid.UUID("00000000-0000-0000-0000-000000000002")
    return lead


# -- context_builder ---------------------------------------------------


def test_system_prompt_includes_memory_context_when_provided() -> None:
    prompt = build_system_prompt(lead=_lead(), research=None, memory_context=MEMORY_BLOCK)

    assert "=== MEMORY CONTEXT ===" in prompt
    assert MEMORY_BLOCK in prompt
    assert prompt.index("=== MEMORY CONTEXT ===") < prompt.index("=== AVAILABLE TOOLS ===")


def test_system_prompt_unchanged_without_memory_context() -> None:
    prompt = build_system_prompt(lead=_lead(), research=None)

    assert "=== MEMORY CONTEXT ===" not in prompt
    assert MEMORY_BLOCK not in prompt
    assert "=== AVAILABLE TOOLS ===" in prompt


# -- brain passthrough --------------------------------------------------


class _ScriptedClient(ProviderClient):
    def __init__(self) -> None:
        self.messages_seen: list[list[LLMMessage]] = []

    @property
    def provider(self) -> str:
        return "openai"

    @property
    def model(self) -> str:
        return "gpt-4o-mini"

    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        tools=None,
        temperature=None,
        max_tokens=None,
        stream: bool = False,
    ) -> ChatResult:
        self.messages_seen.append(list(messages))
        return ChatResult(
            "done", LLMUsage("openai", "gpt-4o-mini", 1, 0, 0.0), "gpt-4o-mini", "stop"
        )


@pytest.mark.asyncio
async def test_brain_forwards_memory_context_into_system_prompt() -> None:
    client = _ScriptedClient()
    brain = Brain(LLMService(client), ToolRegistry())

    result = await brain.run(
        goal="g",
        lead=_lead(),
        research=None,
        memory_context=MEMORY_BLOCK,
    )

    assert result.success is True
    system_message = client.messages_seen[0][0]
    assert system_message.role is MessageRole.SYSTEM
    assert MEMORY_BLOCK in system_message.content


@pytest.mark.asyncio
async def test_brain_without_memory_context_prompt_is_clean() -> None:
    client = _ScriptedClient()
    brain = Brain(LLMService(client), ToolRegistry())

    await brain.run(goal="g", lead=_lead(), research=None)

    system_message = client.messages_seen[0][0]
    assert "=== MEMORY CONTEXT ===" not in system_message.content


# -- ai_service gating + fail-open ----------------------------------------


class _NoOrgSession:
    async def get(self, model: Any, pk: Any) -> None:  # noqa: ANN401
        return None


async def test_retrieve_memory_context_disabled_returns_none(monkeypatch) -> None:
    monkeypatch.setattr(settings, "AI_MEMORY_ENABLED", False)
    service = AIService(_NoOrgSession())

    assert await service._retrieve_memory_context(ORG_ID) is None


async def test_retrieve_memory_context_enabled_returns_block(monkeypatch) -> None:
    monkeypatch.setattr(settings, "AI_MEMORY_ENABLED", True)

    class _Svc:
        def __init__(self, session: object) -> None:
            pass

        async def retrieve_context(self, organization_id: uuid.UUID) -> str:
            return MEMORY_BLOCK

    monkeypatch.setattr("app.services.memory_service.MemoryService", _Svc)
    service = AIService(_NoOrgSession())

    assert await service._retrieve_memory_context(ORG_ID) == MEMORY_BLOCK


async def test_retrieve_memory_context_fails_open(monkeypatch) -> None:
    monkeypatch.setattr(settings, "AI_MEMORY_ENABLED", True)

    class _Boom:
        def __init__(self, session: object) -> None:
            pass

        async def retrieve_context(self, organization_id: uuid.UUID) -> str:
            raise RuntimeError("database unreachable")

    monkeypatch.setattr("app.services.memory_service.MemoryService", _Boom)
    service = AIService(_NoOrgSession())

    assert await service._retrieve_memory_context(ORG_ID) is None
