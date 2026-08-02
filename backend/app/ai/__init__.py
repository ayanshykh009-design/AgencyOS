"""AI Brain package.

Public API:
- Brain / BrainConfig / BrainResult (orchestrator)
- build_system_prompt / build_message_history (context_builder)
- plan_for_goal / Plan / PlanStep (planner)
"""

from app.ai.brain import Brain, BrainConfig, BrainResult
from app.ai.context_builder import build_message_history, build_system_prompt
from app.ai.planner import Plan, PlanStep, all_known_goals, plan_for_goal

__all__ = [
    "Brain",
    "BrainConfig",
    "BrainResult",
    "build_message_history",
    "build_system_prompt",
    "Plan",
    "PlanStep",
    "all_known_goals",
    "plan_for_goal",
]
