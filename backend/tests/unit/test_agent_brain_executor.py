"""Unit tests for the M5 brain-backed executors.

Covers the executor wiring layer: LLM resolution (fail-open), lead-scoped vs
leadless scoping, memory-context retrieval gating, and the BrainResult ->
ExecutorResult mapping. The Brain, LLM service, tool registry, and memory
service are mocked; no database or network is involved.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.executors.base import ExecutorContext
from app.agents.executors.brain_executor import (
    AIBrainExecutor,
    OutreachAgentExecutor,
    ResearchAgentExecutor,
)
from app.ai.brain import BrainResult
from app.core.config import settings
from app.core.errors import AppError

ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
RUN_ID = uuid.UUID("00000000-0000-0000-0000-000000000202")
LEAD_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")


def _ctx(**overrides) -> ExecutorContext:
    kwargs = dict(
        session=MagicMock(),
        organization_id=ORG_ID,
        run_id=RUN_ID,
        goal="research_lead",
        input={"lead_id": str(LEAD_ID)},
    )
    kwargs.update(overrides)
    return ExecutorContext(**kwargs)


def _configure_brain(success: bool, *, response: str = "ok", error: str | None = None):
    brain_cls = MagicMock()
    brain_cls.return_value.run_with_plan = AsyncMock(
        return_value=BrainResult(
            success=success,
            response=response if success else None,
            error=error,
            steps_taken=3,
        )
    )
    return brain_cls


@patch("app.llm.service.LLMService")
@patch("app.tools.registry.default_registry")
@patch("app.ai.brain.Brain")
@pytest.mark.asyncio
async def test_research_agent_success_maps_to_result(brain, default_registry, llm) -> None:
    brain_cls = _configure_brain(True, response="lead researched")
    brain.return_value = brain_cls.return_value
    llm.for_provider.return_value = MagicMock()
    default_registry.return_value = MagicMock()
    lead = MagicMock(id=LEAD_ID)

    with (
        patch(
            "app.agents.executors.brain_executor.resolve_ai_config",
            AsyncMock(return_value=("openai", "gpt-4o")),
        ),
        patch("app.agents.executors.brain_executor.LeadRepository") as lead_repo,
        patch("app.agents.executors.brain_executor.LeadResearchRepository") as research_repo,
        patch.object(settings, "AI_MEMORY_ENABLED", False),
    ):
        lead_repo.return_value.get_or_404 = AsyncMock(return_value=lead)
        research_repo.return_value.get = AsyncMock(return_value=None)
        executor = ResearchAgentExecutor(http_client=MagicMock())
        result = await executor.execute(_ctx())

    assert result.success is True
    assert result.output["response"] == "lead researched"
    assert result.steps == 3
    lead_repo.return_value.get_or_404.assert_awaited_once_with(ORG_ID, LEAD_ID)


@patch("app.llm.service.LLMService")
@patch("app.tools.registry.default_registry")
@patch("app.ai.brain.Brain")
@pytest.mark.asyncio
async def test_brain_failure_maps_to_executor_failure(brain, default_registry, llm) -> None:
    brain_cls = _configure_brain(False, error="max steps (8) reached")
    brain.return_value = brain_cls.return_value
    llm.for_provider.return_value = MagicMock()
    default_registry.return_value = MagicMock()

    with (
        patch(
            "app.agents.executors.brain_executor.resolve_ai_config",
            AsyncMock(return_value=("openai", "gpt-4o")),
        ),
        patch("app.agents.executors.brain_executor.LeadRepository") as lead_repo,
        patch("app.agents.executors.brain_executor.LeadResearchRepository") as research_repo,
        patch.object(settings, "AI_MEMORY_ENABLED", False),
    ):
        lead_repo.return_value.get_or_404 = AsyncMock(return_value=MagicMock(id=LEAD_ID))
        research_repo.return_value.get = AsyncMock(return_value=None)
        executor = OutreachAgentExecutor(http_client=MagicMock())
        result = await executor.execute(_ctx())

    assert result.success is False
    assert result.error == "max steps (8) reached"


@pytest.mark.asyncio
async def test_llm_not_configured_returns_clean_error() -> None:
    with (
        patch(
            "app.agents.executors.brain_executor.resolve_ai_config",
            AsyncMock(side_effect=AppError("ai.invalid_provider", "unsupported", 400)),
        ),
        patch.object(settings, "AI_MEMORY_ENABLED", False),
    ):
        executor = AIBrainExecutor(http_client=MagicMock())
        result = await executor.execute(_ctx(goal="analyze", input={}))

    assert result.success is False
    assert "LLM is not configured" in (result.error or "")


@patch("app.llm.service.LLMService")
@pytest.mark.asyncio
async def test_missing_lead_returns_clean_error(llm) -> None:
    llm.for_provider.return_value = MagicMock()
    with (
        patch(
            "app.agents.executors.brain_executor.resolve_ai_config",
            AsyncMock(return_value=("openai", "gpt-4o")),
        ),
        patch("app.agents.executors.brain_executor.LeadRepository") as lead_repo,
        patch.object(settings, "AI_MEMORY_ENABLED", False),
    ):
        lead_repo.return_value.get_or_404 = AsyncMock(
            side_effect=AppError("lead.not_found", "Not found", 404)
        )
        executor = ResearchAgentExecutor(http_client=MagicMock())
        result = await executor.execute(_ctx())

    assert result.success is False
    assert "lead does not exist" in (result.error or "")


@patch("app.llm.service.LLMService")
@pytest.mark.asyncio
async def test_leadless_executor_never_queries_lead_repo(llm) -> None:
    llm.for_provider.return_value = MagicMock()
    with (
        patch(
            "app.agents.executors.brain_executor.resolve_ai_config",
            AsyncMock(return_value=("openai", "gpt-4o")),
        ),
        patch("app.agents.executors.brain_executor.LeadRepository") as lead_repo,
        patch("app.ai.brain.Brain") as brain,
        patch.object(settings, "AI_MEMORY_ENABLED", False),
    ):
        brain_cls = _configure_brain(True, response="digest")
        brain.return_value = brain_cls.return_value
        executor = AIBrainExecutor(http_client=MagicMock())
        result = await executor.execute(_ctx(goal="summarize", input={"lead_id": str(LEAD_ID)}))

    assert result.success is True
    lead_repo.assert_not_called()
