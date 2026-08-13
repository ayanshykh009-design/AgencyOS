"""Brain-backed agent executors — M5 runtime implementation layer.

Wires the M4 components together for one run without duplicating them:

* the deterministic :mod:`app.ai.planner` provides the goal -> tool sequence,
* :class:`app.ai.brain.Brain` runs the bounded LLM + tool loop,
* :class:`app.tools.registry.ToolRegistry` executes tool calls with runtime
  dependencies injected, and
* :class:`app.services.memory_service.MemoryService` supplies ranked memory
  context (gated on ``AI_MEMORY_ENABLED``, fail-open).

Executors are stateless singletons registered against the executor registry;
all per-run state lives in :class:`ExecutorContext`. Each executable agent
maps to one executor (see the module bottom), so the runtime can resolve every
canonical agent.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx

from app.agents.executors.base import ExecutorContext, ExecutorResult
from app.agents.executors.registry import register_executor
from app.core.config import settings
from app.core.errors import AppError
from app.repositories.lead import LeadRepository
from app.repositories.lead_research import LeadResearchRepository
from app.services.llm_settings import resolve_ai_config

_HTTP_TIMEOUT = 15.0
_PLAN_PARAM_KEYS = ("lead_id", "channel", "query")


class BrainAgentExecutor:
    """Base executor: runs the M4 Brain for a goal (planner + tools + memory)."""

    #: Canonical agent name (must match the registry).
    name: str
    description: str
    #: Goal used when the run input carries no explicit ``goal``.
    default_goal: str = ""
    #: When False, a ``lead_id`` in the input loads the lead + research context.
    leadless: bool = False

    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        self._http_client = http_client

    async def execute(self, ctx: ExecutorContext) -> ExecutorResult:
        owns_client = self._http_client is None
        client = self._http_client or httpx.AsyncClient(timeout=_HTTP_TIMEOUT)
        try:
            deps = await self._runtime_deps(ctx, client)
            if deps["llm"] is None:
                return ExecutorResult(
                    success=False,
                    error="LLM is not configured for this organization",
                )
            lead, research, plan_params = await self._load_scope(ctx)
            if lead is None and not self.leadless and "lead_id" in ctx.input:
                return ExecutorResult(
                    success=False,
                    error="The referenced lead does not exist in this organization",
                )

            from app.ai.brain import Brain

            brain = Brain(deps["llm"], deps["registry"])
            goal = ctx.goal or self.default_goal
            result = await brain.run_with_plan(
                goal=goal,
                lead=lead,
                research=research,
                memory_context=deps["memory_context"],
                persona=self.description,
                **plan_params,
            )
            if result.success:
                return ExecutorResult(
                    success=True,
                    output={"response": result.response},
                    steps=result.steps_taken,
                )
            return ExecutorResult(success=False, error=result.error or "Agent execution failed")
        finally:
            if owns_client:
                await client.aclose()

    async def _runtime_deps(
        self, ctx: ExecutorContext, client: httpx.AsyncClient
    ) -> dict[str, Any]:
        """Build (llm, tool_registry, memory_context) for one run.

        Fail-open: an unconfigured/unsupported LLM resolves to ``None`` so the
        executor returns a clean error instead of raising.
        """
        from app.llm.service import LLMService
        from app.services.memory_service import MemoryService
        from app.tools.registry import ToolContext, default_registry

        llm: LLMService | None = None
        try:
            provider, model = await resolve_ai_config(ctx.session, ctx.organization_id)
            llm = LLMService.for_provider(
                provider,
                model=model,
                organization_id=ctx.organization_id,
                session=ctx.session,
                feature="agent.run",
            )
        except Exception:  # noqa: BLE001 - fail open, reported to run
            llm = None

        registry = default_registry(
            ToolContext(
                session=ctx.session,
                organization_id=ctx.organization_id,
                llm_service=llm,
                http_client=client,
            )
        )

        memory_context: str | None = None
        if settings.AI_MEMORY_ENABLED:
            memory_context = await MemoryService(ctx.session).retrieve_context(ctx.organization_id)
        return {"llm": llm, "registry": registry, "memory_context": memory_context}

    async def _load_scope(self, ctx: ExecutorContext) -> tuple[Any, Any, dict[str, Any]]:
        """Load lead + research when a ``lead_id`` is present (lead-scoped goals)."""
        lead = research = None
        plan_params = {
            str(k): str(v) for k, v in ctx.input.items() if k in _PLAN_PARAM_KEYS and v is not None
        }
        raw_lead_id = ctx.input.get("lead_id")
        if raw_lead_id and not self.leadless:
            try:
                lead_id = uuid.UUID(str(raw_lead_id))
            except (ValueError, TypeError):
                return lead, research, plan_params
            try:
                lead = await LeadRepository(ctx.session).get_or_404(ctx.organization_id, lead_id)
                research = await LeadResearchRepository(ctx.session).get(
                    ctx.organization_id, lead.id
                )
            except AppError:
                lead = research = None
        return lead, research, plan_params


class ResearchAgentExecutor(BrainAgentExecutor):
    """Researches a lead (company overview, pain points, tech stack)."""

    name = "research_agent"
    description = (
        "You research B2B leads: gather the company overview, pain points, and tech "
        "stack, and report a concise research summary."
    )
    default_goal = "research_lead"


class OutreachAgentExecutor(BrainAgentExecutor):
    """Searches leads, drafts, and dispatches personalized outreach."""

    name = "outreach_agent"
    description = (
        "You run B2B outreach: search leads, draft personalized email/LinkedIn "
        "messages from research signals, and dispatch them via automation."
    )


class AIBrainExecutor(BrainAgentExecutor):
    """General reasoning agent: LLM + tool loop for arbitrary goals."""

    name = "ai_brain"
    description = (
        "You are a general-purpose agent. Use the available tools to gather data, "
        "draft content, and accomplish the user's goal, then report back concisely."
    )
    leadless = True


class FounderAssistantExecutor(BrainAgentExecutor):
    """Drafts founder briefings and flags business insights."""

    name = "founder_assistant"
    description = (
        "You assist a startup founder: summarize the business state, flag risks and "
        "opportunities, and surface insights from available data."
    )
    leadless = True


class CRMExecutor(BrainAgentExecutor):
    """Manages lead and CRM state within the organization."""

    name = "crm_agent"
    description = (
        "You manage the organization's CRM: update lead records, keep pipelines "
        "consistent, and report on CRM state using the available tools."
    )
    leadless = True


class WorkflowExecutor(BrainAgentExecutor):
    """Runs and inspects workflow executions within the organization."""

    name = "workflow_agent"
    description = (
        "You operate the organization's workflow automation: inspect executions, "
        "diagnose failures, and re-run work using the available tools."
    )
    leadless = True


class NotificationExecutor(BrainAgentExecutor):
    """Summarizes in-app notifications for the requesting user."""

    name = "notification_agent"
    description = (
        "You summarize the user's in-app notifications: group them by topic, "
        "prioritize what needs action, and report a concise digest."
    )
    leadless = True


# Register the canonical executable agents one-to-one with their executors.
register_executor(ResearchAgentExecutor())
register_executor(OutreachAgentExecutor())
register_executor(AIBrainExecutor())
register_executor(FounderAssistantExecutor())
register_executor(CRMExecutor())
register_executor(WorkflowExecutor())
register_executor(NotificationExecutor())
