"""Agent executors subpackage — concrete per-agent run implementations.

Executors are stateless per run and implement the :class:`AgentExecutor`
protocol (see ``base.py``). ``registry.py`` owns the name -> executor lookup;
``brain_executor.py`` provides the canonical executable agents backed by the
M4 Brain. Importing this package registers every canonical agent's executor.
"""

from __future__ import annotations

# Import the concrete executors so every canonical agent is registered on
# package import.
from app.agents.executors import (
    brain_executor,  # noqa: F401
    growth_executor,  # noqa: F401
)
from app.agents.executors.base import (
    AgentExecutor,
    ExecutorContext,
    ExecutorResult,
)
from app.agents.executors.registry import (
    get_executor,
    register_executor,
    registered_executors,
)

__all__ = [
    "AgentExecutor",
    "ExecutorContext",
    "ExecutorResult",
    "get_executor",
    "register_executor",
    "registered_executors",
]
