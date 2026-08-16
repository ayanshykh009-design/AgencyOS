"""M11-C: brain executor wires authorization + trace into the Brain run."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.executors.base import ExecutorContext
from app.agents.executors.brain_executor import ResearchAgentExecutor
from app.ai.brain import BrainResult
from app.core.config import settings
from app.core.permissions import Permission
from app.models.enums import UserRole

ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
RUN_ID = uuid.UUID("00000000-0000-0000-0000-000000000202")
LEAD_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
TRACE_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
ACTOR_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")


def _ctx(**overrides) -> ExecutorContext:
    kwargs = dict(
        session=MagicMock(),
        organization_id=ORG_ID,
        run_id=RUN_ID,
        goal="research_lead",
        input={"lead_id": str(LEAD_ID), "actor_user_id": str(ACTOR_ID)},
        trace_id=TRACE_ID,
    )
    kwargs.update(overrides)
    return ExecutorContext(**kwargs)


def _brain_result() -> BrainResult:
    return BrainResult(
        success=True,
        response="ok",
        steps_taken=2,
        tool_trace=[
            {"tool": "lead_research", "authorized": True, "ok": True}
        ],
    )


@patch("app.llm.service.LLMService")
@patch("app.tools.registry.default_registry")
@patch("app.ai.brain.Brain")
@pytest.mark.asyncio
async def test_executor_passes_auth_and_trace_to_brain(brain, default_registry, llm) -> None:
    brain_cls = MagicMock()
    brain_cls.return_value.run_with_plan = AsyncMock(return_value=_brain_result())
    brain.return_value = brain_cls.return_value
    llm.for_provider.return_value = MagicMock()
    default_registry.return_value = MagicMock()

    actor = MagicMock()
    actor.role = UserRole.MEMBER

    with (
        patch(
            "app.agents.executors.brain_executor.resolve_ai_config",
            AsyncMock(return_value=("openai", "gpt-4o")),
        ),
        patch("app.agents.executors.brain_executor.LeadRepository") as lead_repo,
        patch("app.agents.executors.brain_executor.LeadResearchRepository") as research_repo,
        patch("app.agents.executors.brain_executor.UserRepository") as user_repo,
        patch.object(settings, "AI_MEMORY_ENABLED", False),
    ):
        lead_repo.return_value.get_or_404 = AsyncMock(return_value=MagicMock(id=LEAD_ID))
        research_repo.return_value.get = AsyncMock(return_value=None)
        user_repo.return_value.get = AsyncMock(return_value=actor)

        executor = ResearchAgentExecutor(http_client=MagicMock())
        result = await executor.execute(_ctx())

    assert result.success is True
    kwargs = brain.return_value.run_with_plan.call_args.kwargs
    assert isinstance(kwargs["caller_permissions"], frozenset)
    assert Permission.LEAD_READ in kwargs["caller_permissions"]
    assert kwargs["allowed_tools"] == {"lead_research", "lead_search", "web_search"}
    assert kwargs["organization_id"] == ORG_ID
    assert kwargs["trace_id"] == TRACE_ID
    assert kwargs["run_id"] == RUN_ID

    # The audit trail + trace id are surfaced in the executor output.
    assert result.output["tool_trace"] == [
        {"tool": "lead_research", "authorized": True, "ok": True}
    ]
    assert result.output["trace_id"] == str(TRACE_ID)
    assert result.output["goal"] == "research_lead"
    assert result.output["organization_id"] == str(ORG_ID)
    assert result.output["run_id"] == str(RUN_ID)


@patch("app.llm.service.LLMService")
@patch("app.tools.registry.default_registry")
@patch("app.ai.brain.Brain")
@pytest.mark.asyncio
async def test_executor_trusted_admin_path_skips_enforcement(brain, default_registry, llm) -> None:
    """Runs created without an actor (trusted AGENT_MANAGE path) skip M11
    enforcement to preserve pre-existing behavior; the AI run path always sets
    an actor and is therefore always enforced."""
    brain_cls = MagicMock()
    brain_cls.return_value.run_with_plan = AsyncMock(return_value=_brain_result())
    brain.return_value = brain_cls.return_value
    llm.for_provider.return_value = MagicMock()
    default_registry.return_value = MagicMock()

    # No actor_user_id in the input.
    with (
        patch(
            "app.agents.executors.brain_executor.resolve_ai_config",
            AsyncMock(return_value=("openai", "gpt-4o")),
        ),
        patch("app.agents.executors.brain_executor.LeadRepository") as lead_repo,
        patch("app.agents.executors.brain_executor.LeadResearchRepository") as research_repo,
        patch("app.agents.executors.brain_executor.UserRepository") as user_repo,
        patch.object(settings, "AI_MEMORY_ENABLED", False),
    ):
        lead_repo.return_value.get_or_404 = AsyncMock(return_value=MagicMock(id=LEAD_ID))
        research_repo.return_value.get = AsyncMock(return_value=None)

        executor = ResearchAgentExecutor(http_client=MagicMock())
        result = await executor.execute(_ctx(input={"lead_id": str(LEAD_ID)}))

    assert result.success is True
    kwargs = brain.return_value.run_with_plan.call_args.kwargs
    assert kwargs["caller_permissions"] is None
    assert kwargs["allowed_tools"] is None
    user_repo.return_value.get.assert_not_called()
