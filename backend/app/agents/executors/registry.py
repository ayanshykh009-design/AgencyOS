"""Executor registry — name -> AgentExecutor lookup for the runtime.

Executors are stateless per run and implement the :class:`AgentExecutor`
protocol. Each executable agent registers exactly one executor at import time
via :func:`register_executor`; the runtime resolves executors through
:func:`get_executor`. Duplicate registrations are a programming error and fail
loudly at import time.
"""

from __future__ import annotations

from app.agents.executors.base import AgentExecutor

_EXECUTORS: dict[str, AgentExecutor] = {}


def register_executor(executor: AgentExecutor) -> None:
    """Register one executor, keyed by its agent name (idempotent-by-fail)."""
    if executor.name in _EXECUTORS:
        raise RuntimeError(f"duplicate executor registered for agent {executor.name!r}")
    _EXECUTORS[executor.name] = executor


def get_executor(name: str) -> AgentExecutor | None:
    """Return the executor for ``name``, or ``None`` when not registered.

    ``None`` means the agent is executable but its executor is not wired yet;
    the runtime fails such runs rather than leaving them queued.
    """
    return _EXECUTORS.get(name)


def registered_executors() -> list[str]:
    """Names of agents that currently have a registered executor."""
    return list(_EXECUTORS)
