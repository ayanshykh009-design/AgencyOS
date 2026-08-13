"""Agent registry — canonical metadata for the M5 agent set.

M1 registered the full Phase 5D agent inventory; M5 makes a strict subset
executable. ``AgentCategory`` expresses exactly what the runtime permits:
``executable`` agents have a run loop, ``registered`` agents are tracked but
not yet executed (their run requests are rejected), and ``future`` agents are
reserved names with no run records at all.

The canonical inventory is a closed set validated at import time (duplicate
names are a programming error, not a runtime case). Executors map one-to-one
with executable agents; see ``app/agents/executors/``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.core.errors import AppError


class AgentCategory(StrEnum):
    """What a registry entry is permitted to do in the runtime."""

    EXECUTABLE = "executable"
    REGISTERED = "registered"
    FUTURE = "future"


@dataclass(frozen=True)
class AgentDefinition:
    """Static metadata for one agent in the canonical registry."""

    name: str
    display_name: str
    description: str
    category: AgentCategory
    supported_goals: tuple[str, ...] = ()


# Canonical agent inventory (Phase 5D architecture). Only EXECUTABLE agents
# may be dispatched by the runtime; REGISTERED/FUTURE entries exist for
# bookkeeping and are refused at run creation time.
CANONICAL_AGENTS: tuple[AgentDefinition, ...] = (
    AgentDefinition(
        name="ai_brain",
        display_name="AI Brain",
        description=(
            "General reasoning agent: orchestrates the LLM + tool loop for arbitrary goals."
        ),
        category=AgentCategory.EXECUTABLE,
    ),
    AgentDefinition(
        name="founder_assistant",
        display_name="Founder Assistant",
        description="Drafts founder briefings and flags business insights for the organization.",
        category=AgentCategory.EXECUTABLE,
    ),
    AgentDefinition(
        name="research_agent",
        display_name="Research Agent",
        description="Researches leads (company overview, pain points, tech stack) on demand.",
        category=AgentCategory.EXECUTABLE,
        supported_goals=("research_lead",),
    ),
    AgentDefinition(
        name="crm_agent",
        display_name="CRM Agent",
        description="Manages lead and CRM state within the organization.",
        category=AgentCategory.EXECUTABLE,
    ),
    AgentDefinition(
        name="outreach_agent",
        display_name="Outreach Agent",
        description="Searches leads, drafts, and dispatches personalized outreach across channels.",
        category=AgentCategory.EXECUTABLE,
        supported_goals=(
            "search_leads",
            "draft_email",
            "draft_linkedin",
            "dispatch_outreach",
            "enrich_and_dispatch",
        ),
    ),
    AgentDefinition(
        name="workflow_agent",
        display_name="Workflow Agent",
        description="Runs and inspects workflow executions within the organization.",
        category=AgentCategory.EXECUTABLE,
    ),
    AgentDefinition(
        name="notification_agent",
        display_name="Notification Agent",
        description="Summarizes in-app notifications for the requesting user.",
        category=AgentCategory.EXECUTABLE,
    ),
    AgentDefinition(
        name="growth_agent",
        display_name="Growth Agent",
        description=(
            "Runs deterministic growth intelligence: KPIs, pipeline, funnel, "
            "conversion, revenue, activity, bottlenecks, opportunities, trends, "
            "health scoring, forecasts, and what-if scenarios."
        ),
        category=AgentCategory.EXECUTABLE,
    ),
    AgentDefinition(
        name="finance",
        display_name="Finance Agent",
        description="Reserved for a future finance capability; not executable.",
        category=AgentCategory.FUTURE,
    ),
    AgentDefinition(
        name="hr",
        display_name="HR Agent",
        description="Reserved for a future HR capability; not executable.",
        category=AgentCategory.FUTURE,
    ),
    AgentDefinition(
        name="calendar",
        display_name="Calendar Agent",
        description="Reserved for a future calendar capability; not executable.",
        category=AgentCategory.FUTURE,
    ),
    AgentDefinition(
        name="voice",
        display_name="Voice Agent",
        description="Reserved for a future voice capability; not executable.",
        category=AgentCategory.FUTURE,
    ),
)


# Lookup table. Built defensively: duplicate names are a developer error and
# must surface at import time, never as a runtime ambiguity.
AGENTS_BY_NAME: dict[str, AgentDefinition] = {}
for _agent in CANONICAL_AGENTS:
    if _agent.name in AGENTS_BY_NAME:
        raise RuntimeError(f"duplicate agent in canonical registry: {_agent.name!r}")
    AGENTS_BY_NAME[_agent.name] = _agent
del _agent


def get_agent(name: str) -> AgentDefinition | None:
    """Return the registry entry for ``name``, or ``None`` when unknown."""
    return AGENTS_BY_NAME.get(name)


def is_known(name: str) -> bool:
    """Whether ``name`` is a canonical agent (executable or not)."""
    return name in AGENTS_BY_NAME


def is_executable(name: str) -> bool:
    """Whether ``name`` may be dispatched by the runtime."""
    agent = get_agent(name)
    return agent is not None and agent.category is AgentCategory.EXECUTABLE


def list_executable() -> list[str]:
    """Names of all executable agents, in canonical order."""
    return [agent.name for agent in CANONICAL_AGENTS if agent.category is AgentCategory.EXECUTABLE]


def require_executable(name: str) -> AgentDefinition:
    """Return the executable definition, or raise 404/409.

    Unknown names are 404s; known but non-executable names (registered-only or
    future agents) are 409 conflicts — the client should not treat them as
    runnable.
    """
    agent = get_agent(name)
    if agent is None:
        raise AppError(
            code="agent.unknown",
            message=f"Unknown agent: {name!r}",
            status_code=404,
        )
    if agent.category is not AgentCategory.EXECUTABLE:
        raise AppError(
            code="agent.not_executable",
            message=f"Agent {name!r} is registered but not executable",
            status_code=409,
        )
    return agent
