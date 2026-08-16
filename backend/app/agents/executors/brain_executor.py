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
from app.ai.planner import allowed_tools_for_goal
from app.core.config import settings
from app.core.errors import AppError
from app.core.permissions import Permission, permissions_for_role
from app.repositories.lead import LeadRepository
from app.repositories.lead_research import LeadResearchRepository
from app.repositories.user import UserRepository
from app.services.founder_intent_service import FounderIntentService
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

            # M11 enforcement context. The AI run surface always carries an
            # ``actor_user_id`` (set by /api/v1/ai/run); when present we resolve
            # the actor's permissions and bound the tool set to the goal's
            # allow-list. Runs created by other (trusted, AGENT_MANAGE) paths do
            # not set an actor, so enforcement is skipped to preserve their
            # existing behavior — the AI run path is the one that requires it.
            goal = ctx.goal or self.default_goal
            actor_id = _uuid_or_none(ctx.input.get("actor_user_id"))
            if actor_id is not None:
                actor = await UserRepository(ctx.session).get(actor_id)
                caller_permissions = (
                    permissions_for_role(actor.role) if actor is not None else frozenset()
                )
                allowed_tools = allowed_tools_for_goal(goal)
            else:
                caller_permissions = None
                allowed_tools = None

            from app.ai.brain import Brain

            brain = Brain(deps["llm"], deps["registry"])
            result = await brain.run_with_plan(
                goal=goal,
                lead=lead,
                research=research,
                memory_context=deps["memory_context"],
                persona=self.description,
                caller_permissions=caller_permissions,
                allowed_tools=allowed_tools,
                organization_id=ctx.organization_id,
                trace_id=ctx.trace_id,
                run_id=ctx.run_id,
                **plan_params,
            )
            if result.success:
                return ExecutorResult(
                    success=True,
                    output={
                        "response": result.response,
                        "tool_trace": result.tool_trace,
                        "trace_id": str(ctx.trace_id) if ctx.trace_id else None,
                        "goal": goal,
                        "organization_id": str(ctx.organization_id),
                        "run_id": str(ctx.run_id),
                    },
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
                feature="ai.agent.run",
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
    """Grounded founder assistant: answers from retrieved context, actions gated.

    Every answer is grounded in a :class:`FounderContext` snapshot; any action is
    routed through :class:`FounderActionService` (and therefore an approval
    request) rather than mutating org data directly.
    """

    name = "founder_assistant"
    description = (
        "You are the Founder AI Assistant: summarize the business state, flag risks "
        "and opportunities, and propose actions (which require approval) using the "
        "provided tools. Never invent data or act without proposing."
    )
    leadless = True

    async def execute(self, ctx: ExecutorContext) -> ExecutorResult:
        if not settings.FOUNDER_ASSISTANT_ENABLED:
            return ExecutorResult(success=False, error="Founder assistant is disabled")

        # Per-org AI kill switch (F-SEC-3): fail closed at the authoritative
        # execution boundary, before any LLM or tool call.
        from app.services.ai_service import AIService

        try:
            await AIService(ctx.session).assert_ai_enabled(ctx.organization_id)
        except AppError as exc:
            return ExecutorResult(success=False, error=exc.message)

        owns_client = self._http_client is None
        client = self._http_client or httpx.AsyncClient(timeout=_HTTP_TIMEOUT)
        try:
            deps = await self._runtime_deps(ctx, client)
            llm = deps["llm"]
            if llm is None:
                return ExecutorResult(
                    success=False,
                    error="LLM is not configured for this organization",
                )

            message = (ctx.input.get("message") or "").strip()
            actor_user_id = _uuid_or_none(ctx.input.get("actor_user_id"))
            conversation_id = _uuid_or_none(ctx.input.get("conversation_id"))

            # M11 enforcement context — mirror the main AI run executor: resolve
            # the actor's permissions and bound the tool set to the founder
            # assistant goal's allow-list so founder tools are authorized through
            # the same primitive as every other AI run.
            caller_permissions: frozenset[Permission] | None = None
            allowed_tools: set[str] | None = None
            if actor_user_id is not None:
                actor = await UserRepository(ctx.session).get(actor_user_id)
                caller_permissions = (
                    permissions_for_role(actor.role) if actor is not None else frozenset()
                )
                allowed_tools = allowed_tools_for_goal("founder_assistant")

            from app.ai.founder_context import FounderContextBuilder
            from app.services.founder_action_service import FounderActionService
            from app.tools.founder_tools import FounderToolContext, founder_registry

            context = await FounderContextBuilder(ctx.session, ctx.organization_id).build()
            intent = FounderIntentService.classify(message)

            action_service = FounderActionService(ctx.session)
            tool_ctx = FounderToolContext(
                session=ctx.session,
                organization_id=ctx.organization_id,
                context=context,
                action_service=action_service,
                llm_service=llm,
                http_client=client,
                conversation_id=conversation_id,
                actor_user_id=actor_user_id,
            )
            registry = founder_registry(tool_ctx)

            recent_messages = [{"role": "user", "content": message}] if message else []
            from app.ai.brain import Brain

            brain = Brain(llm, registry)
            result = await brain.run(
                goal="founder_assistant",
                lead=None,
                research=None,
                recent_messages=recent_messages,
                persona=_founder_persona(context, intent),
                caller_permissions=caller_permissions,
                allowed_tools=allowed_tools,
                organization_id=ctx.organization_id,
            )
            if not result.success:
                return ExecutorResult(
                    success=False,
                    error=result.error or "Founder assistant failed",
                    steps=result.steps_taken,
                )

            proposals: list[dict[str, Any]] = []
            if conversation_id is not None:
                from app.repositories.founder_action_proposal import (
                    FounderActionProposalRepository,
                )

                created = await FounderActionProposalRepository(
                    ctx.session
                ).list_by_conversation(ctx.organization_id, conversation_id, limit=50)
                proposals = [
                    {
                        "id": str(p.id),
                        "title": p.title,
                        "action_type": p.action_type.value,
                        "status": p.proposal_status.value,
                    }
                    for p in created
                ]

            return ExecutorResult(
                success=True,
                output={
                    "response": result.response,
                    "tool_calls": [tc.name for tc in (result.tool_calls or [])],
                    "proposals": proposals,
                    "intent": intent.to_dict(),
                },
                steps=result.steps_taken,
            )
        finally:
            if owns_client:
                await client.aclose()


def _uuid_or_none(raw: Any) -> uuid.UUID | None:
    """Best-effort parse of a UUID from arbitrary input."""
    if raw is None:
        return None
    try:
        return uuid.UUID(str(raw))
    except (ValueError, TypeError):
        return None


def _founder_persona(context: Any, intent: Any) -> str:
    """Build the founder assistant system prompt (grounding + tool policy)."""
    lines = [
        "You are the Founder AI Assistant for a B2B agency. You help the founder "
        "understand and run their business using the tools provided.",
        "",
        "GROUNDING RULES (critical):",
        "- Answer ONLY from the provided business context and tool results.",
        "- Never invent metrics, leads, tasks, or approvals that are not present.",
        "- You cannot directly change the business. To take an action (create a "
        "task, send email, run a workflow, export), you MUST call a proposal tool "
        "(create_task or propose_founder_action). Tell the user the action is "
        "pending approval.",
        "- Use summarize_context / get_recent_activity to ground your answer when "
        "the user asks about the business state.",
        "",
        f"INTENT: {intent.intent_type.value if intent else 'status'}",
        "",
        "=== BUSINESS CONTEXT ===",
        context.summary() if context is not None else "",
        "",
        "=== AVAILABLE TOOLS ===",
        "summarize_context, get_recent_activity, growth_analysis, lead_search, "
        "draft_email, create_task, propose_founder_action.",
    ]
    return "\n".join(lines)


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
