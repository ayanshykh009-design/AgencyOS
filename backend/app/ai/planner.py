"""Deterministic planner — maps a high-level goal to an ordered tool sequence.

The planner is stateless and purely rule-based; it does NOT call an LLM. The
brain's LLM loop handles dynamic tool-calling; the planner only provides an
initial suggested sequence for common goal types.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PlanStep:
    """One step in the execution plan."""

    tool: str
    input: dict[str, Any]


@dataclass(frozen=True)
class Plan:
    """Ordered sequence of tool calls to achieve a goal."""

    goal: str
    steps: list[PlanStep]

    def first_tool(self) -> PlanStep | None:
        return self.steps[0] if self.steps else None

    def remaining(self) -> list[PlanStep]:
        return self.steps[1:]


def _tool_call_input(tool: str, **kwargs: Any) -> dict[str, Any]:
    return {"tool": tool, "input": kwargs}


# Goal -> initial tool sequence (can be extended dynamically by the brain).
_GOAL_PLANS: dict[str, list[PlanStep]] = {
    "research_lead": [
        PlanStep(tool="lead_research", input={"lead_id": "{lead_id}"}),
    ],
    "search_leads": [
        PlanStep(tool="lead_search", input={"query": "{query}", "limit": 20}),
    ],
    "draft_email": [
        PlanStep(tool="lead_research", input={"lead_id": "{lead_id}"}),
        PlanStep(tool="draft_outreach", input={"lead_id": "{lead_id}", "channel": "email"}),
    ],
    "draft_linkedin": [
        PlanStep(tool="lead_research", input={"lead_id": "{lead_id}"}),
        PlanStep(tool="draft_outreach", input={"lead_id": "{lead_id}", "channel": "linkedin"}),
    ],
    "dispatch_outreach": [
        PlanStep(tool="draft_outreach", input={"lead_id": "{lead_id}", "channel": "{channel}"}),
        PlanStep(
            tool="n8n_dispatch",
            input={"workflow": "outreach-dispatch", "payload": "{draft_payload}"},
        ),
    ],
    "enrich_and_dispatch": [
        PlanStep(tool="lead_research", input={"lead_id": "{lead_id}"}),
        PlanStep(tool="draft_outreach", input={"lead_id": "{lead_id}", "channel": "email"}),
        PlanStep(
            tool="n8n_dispatch",
            input={"workflow": "outreach-dispatch", "payload": "{draft_payload}"},
        ),
    ],
}


def plan_for_goal(goal: str, **params: Any) -> Plan | None:
    """Return a pre-defined plan for the goal with parameters interpolated."""
    template = _GOAL_PLANS.get(goal)
    if template is None:
        return None

    steps: list[PlanStep] = []
    for step in template:
        # Interpolate {param} placeholders in the step input.
        interpolated_input: dict[str, Any] = {}
        for k, v in step.input.items():
            if isinstance(v, str):
                for param_name, param_val in params.items():
                    v = v.replace(f"{{{param_name}}}", str(param_val))
            interpolated_input[k] = v
        steps.append(PlanStep(tool=step.tool, input=interpolated_input))

    return Plan(goal=goal, steps=steps)


def all_known_goals() -> list[str]:
    return list(_GOAL_PLANS.keys())
