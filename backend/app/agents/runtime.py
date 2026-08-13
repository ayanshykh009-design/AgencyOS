"""Agent runtime — the guarded executor lifecycle for one agent run.

The runtime turns a QUEUED :class:`AgentRun` into a finished one:

1. resolve the executor for the run's agent (unresolved -> fail the run);
2. claim the run (QUEUED -> RUNNING) via a guarded transition, so a second
   worker racing on the same run simply skips it;
3. build an :class:`ExecutorContext` and run the executor under a hard timeout
   (``AGENT_RUN_TIMEOUT_SECONDS``);
4. land on a terminal state via guarded transitions (``complete_run`` /
   ``fail_run``), which honour a concurrent cancel flag by producing CANCELLED.

All persistence goes through ``AgentService`` guarded transitions; executors
never touch run rows. Unexpected exceptions are sanitized (no stack traces)
before persisting ``agent_runs.error``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.executors import AgentExecutor, ExecutorContext, get_executor
from app.core.config import settings
from app.core.errors import AppError
from app.models.agent_run import AgentRun
from app.services.agent_service import AgentService

_EXECUTOR_RESOLVER = Callable[[str], AgentExecutor | None]


class AgentRuntime:
    """Orchestrates one queued run through the guarded executor lifecycle."""

    def __init__(
        self,
        *,
        llm_service=None,
        tool_registry=None,
        memory_service=None,
        resolve_executor: _EXECUTOR_RESOLVER = get_executor,
    ) -> None:
        self._llm_service = llm_service
        self._tool_registry = tool_registry
        self._memory_service = memory_service
        self._resolve_executor = resolve_executor

    async def execute_run(self, session: AsyncSession, run: AgentRun) -> AgentRun | None:
        """Claim and execute one queued run.

        Returns the final run row (SUCCEEDED / FAILED / CANCELLED) or ``None``
        when the run was already claimed or finalised by another worker/sweep.
        """
        service = AgentService(session)

        executor = self._resolve_executor(run.agent_name)
        if executor is None:
            try:
                return await service.fail_queued_run(
                    run.organization_id,
                    run.id,
                    error=f"Agent {run.agent_name!r} has no registered executor",
                )
            except AppError:
                return None

        try:
            await service.start_run(run.organization_id, run.id)
        except AppError:
            # Already claimed (or cancelled) by a concurrent worker.
            return None

        context = ExecutorContext(
            session=session,
            organization_id=run.organization_id,
            run_id=run.id,
            goal=self._goal_for(run),
            input=run.input,
            llm_service=self._llm_service,
            tool_registry=self._tool_registry,
            memory_service=self._memory_service,
        )
        try:
            result = await asyncio.wait_for(
                executor.execute(context),
                timeout=settings.AGENT_RUN_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            return await self._finish(service, run, error="Agent run exceeded its time budget")
        except Exception as exc:  # noqa: BLE001 - any executor failure lands FAILED
            return await self._finish(service, run, error=self._sanitize(exc))
        if result.success:
            return await self._finish(service, run, output=result.output, cost=result.cost)
        return await self._finish(service, run, error=result.error or "Agent execution failed")

    @staticmethod
    def _goal_for(run: AgentRun) -> str:
        """Extract the goal from the run input (empty when absent)."""
        raw = run.input.get("goal") if isinstance(run.input, dict) else None
        return raw if isinstance(raw, str) else ""

    async def _finish(
        self,
        service: AgentService,
        run: AgentRun,
        *,
        output: dict | None = None,
        cost=None,
        error: str | None = None,
    ) -> AgentRun | None:
        """Land the run on a terminal state; ``None`` if already finalised."""
        try:
            if error is not None:
                return await service.fail_run(run.organization_id, run.id, error=error)
            return await service.complete_run(
                run.organization_id,
                run.id,
                output=output or {},
                cost=cost,
            )
        except AppError:
            # Concurrently cancelled / finalised by a worker sweep.
            return None

    @staticmethod
    def _sanitize(exc: Exception) -> str:
        """Turn an unexpected exception into a safe, client-visible message."""
        if isinstance(exc, AppError):
            return exc.message or exc.code
        message = str(exc).strip()
        if not message:
            return "Agent execution failed"
        return message[:500]
