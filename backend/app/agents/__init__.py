"""Agents package: Phase 5D AI agent runtime.

Owns the agent registry, the strict run state machine, the executor contract,
and the ``agent_runs`` / ``agent_state`` bookkeeping for the core and future
agent set (see the approved Phase 5D architecture). Introduced in M1 as the
package scaffold; M5 (Agent Runtime) implements the registry, state machine,
executors, and the agent worker.

Conventions: agents are dependency-injected (import repositories and services,
never endpoints) and the package exports only the public agent manager API.
"""

from app.agents.registry import (
    AGENTS_BY_NAME,
    CANONICAL_AGENTS,
    AgentCategory,
    AgentDefinition,
    get_agent,
    is_executable,
    is_known,
    list_executable,
    require_executable,
)
from app.agents.state_machine import (
    TERMINAL_STATUSES,
    assert_transition,
    can_transition,
    is_cancellable,
    is_terminal,
)

__all__ = [
    "AGENTS_BY_NAME",
    "CANONICAL_AGENTS",
    "AgentCategory",
    "AgentDefinition",
    "TERMINAL_STATUSES",
    "assert_transition",
    "can_transition",
    "get_agent",
    "is_cancellable",
    "is_executable",
    "is_known",
    "is_terminal",
    "list_executable",
    "require_executable",
]
