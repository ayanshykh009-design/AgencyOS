"""AgentRun state machine — strict transition rules for the agent runtime.

The runtime keeps only five statuses (``queued | running | succeeded | failed |
cancelled`` — see ``AgentRunStatus``). This module is the single source of
truth for which transitions are legal; every service-layer status change must
pass through :func:`assert_transition`, and the repository layer enforces the
same rules again with guarded single-statement ``UPDATE``s so a concurrent
worker can never clobber a terminal row.

Terminal statuses (``succeeded | failed | cancelled``) never revert.
"""

from __future__ import annotations

from app.core.errors import AppError
from app.models.enums import AgentRunStatus

# Terminal statuses can never be left once reached.
TERMINAL_STATUSES: frozenset[AgentRunStatus] = frozenset(
    {
        AgentRunStatus.SUCCEEDED,
        AgentRunStatus.FAILED,
        AgentRunStatus.CANCELLED,
    }
)

# Only these transitions are legal. Adding a status to ``AgentRunStatus``
# without updating this table fails the completeness test in the unit suite.
_ALLOWED_TRANSITIONS: dict[AgentRunStatus, frozenset[AgentRunStatus]] = {
    # A queued run may be claimed by the worker, fail before dispatch (agent
    # disabled/unknown), or be cancelled while still pending.
    AgentRunStatus.QUEUED: frozenset(
        {
            AgentRunStatus.RUNNING,
            AgentRunStatus.FAILED,
            AgentRunStatus.CANCELLED,
        }
    ),
    # A running run may complete, fail, or be cancelled in flight (after a
    # cancel request set ``cancel_requested_at``).
    AgentRunStatus.RUNNING: frozenset(
        {
            AgentRunStatus.SUCCEEDED,
            AgentRunStatus.FAILED,
            AgentRunStatus.CANCELLED,
        }
    ),
    AgentRunStatus.SUCCEEDED: frozenset(),
    AgentRunStatus.FAILED: frozenset(),
    AgentRunStatus.CANCELLED: frozenset(),
}


def is_terminal(status: AgentRunStatus) -> bool:
    """Whether ``status`` is a terminal state (no outgoing transitions)."""
    return status in TERMINAL_STATUSES


def can_transition(from_status: AgentRunStatus, to_status: AgentRunStatus) -> bool:
    """Whether the runtime may move a run from ``from_status`` to ``to_status``."""
    return to_status in _ALLOWED_TRANSITIONS[from_status]


def assert_transition(
    from_status: AgentRunStatus,
    to_status: AgentRunStatus,
    *,
    code: str = "agent_run.illegal_transition",
    message: str | None = None,
) -> None:
    """Raise ``AppError`` (409) when the transition is not legal."""
    if not can_transition(from_status, to_status):
        raise AppError(
            code=code,
            message=message
            or f"Illegal agent run transition: {from_status.value} -> {to_status.value}",
            status_code=409,
        )


def is_cancellable(status: AgentRunStatus) -> bool:
    """A run can be cancelled only while queued or running (never terminal)."""
    return status in (AgentRunStatus.QUEUED, AgentRunStatus.RUNNING)
