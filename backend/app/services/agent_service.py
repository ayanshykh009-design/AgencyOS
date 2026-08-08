"""Agent service: agent run records + per-agent health state.

Thin orchestration over the M2 repositories. The API layer records and reads
runs/states; the actual agent runtime (execution, scheduling) lands in M4 —
this service never executes anything.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.agent_run import AgentRun
from app.models.agent_state import AgentState
from app.models.enums import AgentHealth, AgentRunStatus, AgentRunTrigger, AgentStateStatus
from app.repositories.agent_run import AgentRunRepository
from app.repositories.agent_state import AgentStateRepository
from app.services.base import commit_with_retry


class AgentService:
    """Owns agent run/state rules and the transaction boundary."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._runs = AgentRunRepository(session)
        self._states = AgentStateRepository(session)

    async def list_runs(
        self,
        organization_id: uuid.UUID,
        *,
        agent_name: str | None = None,
        status: AgentRunStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AgentRun]:
        """List runs, optionally scoped to one agent and/or status."""
        if agent_name:
            return await self._runs.list_by_agent(
                organization_id,
                agent_name,
                status=status,
                limit=limit,
                offset=offset,
            )
        return await self._runs.list(
            organization_id,
            limit=limit,
            offset=offset,
            order_by=desc(AgentRun.created_at),
        )

    async def get_run(self, organization_id: uuid.UUID, run_id: uuid.UUID) -> AgentRun:
        return await self._runs.get_or_404(organization_id, run_id)

    async def create_run(
        self,
        organization_id: uuid.UUID,
        *,
        agent_name: str,
        status: AgentRunStatus = AgentRunStatus.QUEUED,
        trigger: AgentRunTrigger = AgentRunTrigger.MANUAL,
        workflow_id: uuid.UUID | None = None,
        input_: dict,
    ) -> AgentRun:
        """Persist a run record (never executed here)."""
        run = AgentRun(
            organization_id=organization_id,
            agent_name=agent_name,
            status=status,
            trigger=trigger,
            workflow_id=workflow_id,
            input=input_,
        )
        self._runs.add(run)
        await commit_with_retry(self._session)
        return run

    async def update_run(
        self,
        organization_id: uuid.UUID,
        run_id: uuid.UUID,
        *,
        status: AgentRunStatus | None = None,
        output: dict | None = None,
        error: str | None = None,
        duration_ms: int | None = None,
        cost: Decimal | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
    ) -> AgentRun:
        """Update a run record in place; commits only when changed."""
        run = await self._runs.get_or_404(organization_id, run_id)
        if status is not None and run.status is not status:
            run.status = status
        if output is not None:
            run.output = output
        if error is not None:
            run.error = error
        if duration_ms is not None:
            run.duration_ms = duration_ms
        if cost is not None:
            run.cost = cost
        if started_at is not None:
            run.started_at = started_at
        if finished_at is not None:
            run.finished_at = finished_at
        await commit_with_retry(self._session)
        return run

    async def list_states(
        self,
        organization_id: uuid.UUID,
        *,
        status: AgentStateStatus | None = None,
        limit: int = 100,
    ) -> list[AgentState]:
        return await self._states.list_by_status(
            organization_id, status=status, limit=limit
        )

    async def upsert_state(
        self,
        organization_id: uuid.UUID,
        *,
        agent_name: str,
        status: AgentStateStatus,
        health: AgentHealth,
        queue_depth: int,
        total_runs: int,
        average_runtime_ms: Decimal,
        average_cost: Decimal,
        last_execution: datetime | None,
        last_error: str | None,
    ) -> AgentState:
        """Upsert the single (org, agent) state row and return it."""
        await self._states.upsert(
            organization_id=organization_id,
            agent_name=agent_name,
            status=status,
            health=health,
            queue_depth=queue_depth,
            total_runs=total_runs,
            average_runtime_ms=average_runtime_ms,
            average_cost=average_cost,
            last_execution=last_execution,
            last_error=last_error,
        )
        await commit_with_retry(self._session)
        state = await self._states.get_by_name(organization_id, agent_name)
        if state is None:  # pragma: no cover - defensive: upsert must create the row
            raise AppError(
                code="agent.state_write_failed",
                message="Failed to persist agent state",
                status_code=500,
            )
        return state
