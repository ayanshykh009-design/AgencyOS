"""Agent executor contract — the unit of runtime execution.

Every canonical agent is backed by exactly one executor. Executors are
stateless per run: the runtime constructs an :class:`ExecutorContext` (session,
run identity, goal, input, plus the lazily-built brain dependencies) and calls
``execute(ctx)``, which returns an :class:`ExecutorResult`. Executors never
touch the HTTP layer and never mutate agent run rows directly — the runtime
owns all persistence.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from app.llm.service import LLMService
    from app.services.memory_service import MemoryService
    from app.tools.registry import ToolRegistry


@dataclass
class ExecutorResult:
    """Outcome of one executor run.

    ``success`` gates everything: on failure ``error`` carries the human-readable
    reason (persisted to ``agent_runs.error``) and ``output`` is ignored.
    """

    success: bool
    output: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    steps: int = 0
    duration_ms: int = 0
    cost: Decimal = field(default_factory=lambda: Decimal("0"))


@dataclass
class ExecutorContext:
    """Dependencies and inputs handed to an executor for one run.

    ``llm_service`` / ``tool_registry`` / ``memory_service`` are constructed by
    the runtime (gated on their feature flags) and injected so executors stay
    decoupled from wiring.
    """

    session: AsyncSession
    organization_id: uuid.UUID
    run_id: uuid.UUID
    goal: str
    input: dict[str, Any]
    llm_service: LLMService | None = None
    tool_registry: ToolRegistry | None = None
    memory_service: MemoryService | None = None
    trace_id: uuid.UUID | None = None


@runtime_checkable
class AgentExecutor(Protocol):
    """Contract every canonical agent executor satisfies."""

    name: str
    description: str

    async def execute(self, ctx: ExecutorContext) -> ExecutorResult: ...
