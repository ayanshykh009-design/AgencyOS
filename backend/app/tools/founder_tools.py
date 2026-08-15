"""Founder assistant tools.

The founder tool set is a *curated composition*:

- founder-native tools that operate on the grounded :class:`FounderContext` and
  route any write through :class:`FounderActionService` (which gates every
  action behind an ``ApprovalRequest``); and
- existing, general tools (``growth_analysis``, ``lead_search``, ``draft_email``)
  reused verbatim via their ``instantiate`` builders — no duplicated logic.

Every mutating tool returns a proposal id; the assistant never writes org data
directly.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.founder_context import FounderContext
from app.models.enums import FounderActionType
from app.tools.base import ToolResult
from app.tools.registry import ToolContext, ToolRegistry


@dataclass
class FounderToolContext:
    """Runtime dependencies injected into the founder tools."""

    session: AsyncSession
    organization_id: uuid.UUID
    context: FounderContext
    action_service: Any
    llm_service: Any = None
    http_client: Any = None
    conversation_id: uuid.UUID | None = None
    actor_user_id: uuid.UUID | None = None


class FounderTool:
    """Base class for founder-native tools (satisfies the ``Tool`` protocol)."""

    name: str = ""
    description: str = ""
    parameters: dict[str, Any] = {"type": "object", "properties": {}}

    def __init__(self, ctx: FounderToolContext) -> None:
        self._ctx = ctx

    async def run(self, input: dict[str, Any]) -> ToolResult:  # pragma: no cover - abstract
        raise NotImplementedError


class SummarizeContextTool(FounderTool):
    """Return a compact, grounded summary of the founder's business context."""

    name = "summarize_context"
    description = (
        "Summarize the founder's current business context: organization, KPI "
        "snapshot, recent leads, open tasks, pending approvals and open "
        "founder proposals. Use this to ground answers."
    )
    parameters = {"type": "object", "properties": {}}

    async def run(self, input: dict[str, Any]) -> ToolResult:
        return ToolResult(ok=True, content=self._ctx.context.summary())


class GetRecentActivityTool(FounderTool):
    """Return the recent-activity snapshot (leads/tasks/executions/approvals)."""

    name = "get_recent_activity"
    description = (
        "List recent activity across the org: recent leads, open tasks, recent "
        "workflow executions, pending approvals and open founder proposals."
    )
    parameters = {
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
        },
    }

    async def run(self, input: dict[str, Any]) -> ToolResult:
        ctx = self._ctx.context
        return ToolResult(
            ok=True,
            content={
                "leads": ctx.leads,
                "tasks": ctx.tasks,
                "executions": ctx.executions,
                "pending_approvals": ctx.pending_approvals,
                "open_proposals": ctx.open_proposals,
            },
        )


class CreateTaskTool(FounderTool):
    """Propose creating a team task (approval-gated, never created directly)."""

    name = "create_task"
    description = (
        "Propose creating a task for the team. The task is NOT created until the "
        "proposal is approved. Returns the proposal id."
    )
    parameters = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Task title."},
            "description": {"type": "string", "description": "Optional task description."},
            "priority": {
                "type": "string",
                "enum": ["low", "medium", "high", "urgent"],
                "default": "medium",
            },
            "due_at": {
                "type": "string",
                "format": "date-time",
                "description": "Optional due date.",
            },
            "assignee_user_id": {
                "type": "string",
                "description": "Optional assignee user id.",
            },
        },
        "required": ["title"],
    }

    async def run(self, input: dict[str, Any]) -> ToolResult:
        title = (input.get("title") or "").strip()
        if not title:
            return ToolResult(ok=False, error="create_task requires a non-empty 'title'")
        proposal = await self._ctx.action_service.propose(
            organization_id=self._ctx.organization_id,
            actor_user_id=self._ctx.actor_user_id,
            conversation_id=self._ctx.conversation_id,
            action_type=FounderActionType.CREATE_TASK,
            title=f"Create task: {title}",
            payload={
                "title": title,
                "description": input.get("description"),
                "priority": input.get("priority", "medium"),
                "due_at": input.get("due_at"),
                "assignee_user_id": input.get("assignee_user_id"),
            },
            justification=input.get("justification"),
        )
        return ToolResult(
            ok=True,
            content={
                "proposal_id": str(proposal.id),
                "title": proposal.title,
                "status": proposal.proposal_status.value,
                "requires_approval": True,
            },
        )


class ProposeFounderActionTool(FounderTool):
    """Generic proposal creator for any supported founder action type."""

    name = "propose_founder_action"
    description = (
        "Propose a founder action for approval. action_type is one of: "
        + ", ".join(e.value for e in FounderActionType)
        + ". Returns the proposal id."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action_type": {
                "type": "string",
                "enum": [e.value for e in FounderActionType],
            },
            "title": {"type": "string", "description": "Human-readable title."},
            "payload": {"type": "object", "description": "Action-specific parameters."},
            "justification": {"type": "string", "description": "Why this action is proposed."},
        },
        "required": ["action_type", "title"],
    }

    async def run(self, input: dict[str, Any]) -> ToolResult:
        raw = input.get("action_type")
        try:
            action_type = FounderActionType(str(raw))
        except ValueError:
            return ToolResult(ok=False, error=f"unknown action_type {raw!r}")
        title = (input.get("title") or "").strip()
        if not title:
            return ToolResult(ok=False, error="propose_founder_action requires a non-empty 'title'")
        proposal = await self._ctx.action_service.propose(
            organization_id=self._ctx.organization_id,
            actor_user_id=self._ctx.actor_user_id,
            conversation_id=self._ctx.conversation_id,
            action_type=action_type,
            title=title,
            payload=input.get("payload") or {},
            justification=input.get("justification"),
        )
        return ToolResult(
            ok=True,
            content={
                "proposal_id": str(proposal.id),
                "title": proposal.title,
                "status": proposal.proposal_status.value,
                "requires_approval": True,
            },
        )


def founder_registry(tool_ctx: FounderToolContext) -> ToolRegistry:
    """Build a founder tool registry: native tools + reused general tools.

    Reused general tools (``growth_analysis``, ``lead_search``, ``draft_email``)
    are composed via their ``instantiate`` builders and skipped if their
    backend is unavailable (mirrors ``default_registry`` behavior).
    """
    registry = ToolRegistry()
    registry.register(SummarizeContextTool(tool_ctx))
    registry.register(GetRecentActivityTool(tool_ctx))
    registry.register(CreateTaskTool(tool_ctx))
    registry.register(ProposeFounderActionTool(tool_ctx))

    tc = ToolContext(
        session=tool_ctx.session,
        organization_id=tool_ctx.organization_id,
        llm_service=tool_ctx.llm_service,
        http_client=tool_ctx.http_client,
    )

    try:
        from app.tools.growth_tool import GrowthAnalysisTool

        registry.register(GrowthAnalysisTool.instantiate(tc))
    except ImportError:
        pass

    try:
        from app.tools.lead_search_tool import LeadSearchTool

        registry.register(LeadSearchTool.instantiate(tc))
    except ImportError:
        pass

    if tool_ctx.llm_service is not None:
        try:
            from app.tools.email_draft_tool import EmailDraftTool

            registry.register(EmailDraftTool.instantiate(tc))
        except ImportError:
            pass

    return registry
