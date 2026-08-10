"""Agent service: agent run records + per-agent health state.

M2/M3 thin orchestration over the repositories; M5 adds the runtime-owned
run lifecycle. All state transitions go through guarded single-statement
``UPDATE ... RETURNING`` calls (see ``AgentRunRepository``) so concurrent
workers and cancels can never clobber each other. Status is runtime-owned:
``update_run`` (the user-facing PATCH path) accepts no status, and
``create_run`` refuses any initial status other than QUEUED.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import desc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.registry import require_executable
from app.agents.state_machine import assert_transition, is_cancellable
from app.core.errors import AppError
from app.core.metrics import get_counter
from app.models.agent_run import AgentRun
from app.models.agent_state import AgentState
from app.models.enums import AgentHealth, AgentRunStatus, AgentRunTrigger, AgentStateStatus
from app.repositories.agent_run import AgentRunRepository
from app.repositories.agent_state import AgentStateRepository
from app.services.base import commit_with_retry, utcnow


class AgentService:
    """Owns agent run/state rules and the transaction boundary."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._runs = AgentRunRepository(session)
        self._states = AgentStateRepository(session)

    # -- run reads -----------------------------------------------------

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

    # -- run creation --------------------------------------------------

    async def create_run(
        self,
        organization_id: uuid.UUID,
        *,
        agent_name: str,
        status: AgentRunStatus = AgentRunStatus.QUEUED,
        trigger: AgentRunTrigger = AgentRunTrigger.MANUAL,
        workflow_id: uuid.UUID | None = None,
        input_: dict,
        idempotency_key: str | None = None,
    ) -> AgentRun:
        """Queue a run for an executable agent.

        Refuses unknown agents (404) and registered-only/future agents (409).
        The initial status must be QUEUED — the runtime owns every subsequent
        transition. With an idempotency key, re-creating an identical run
        returns the existing row instead of queuing a duplicate.
        """
        require_executable(agent_name)
        if status is not AgentRunStatus.QUEUED:
            raise AppError(
                code="agent_run.invalid_initial_status",
                message="Agent runs must be created as queued",
                status_code=400,
            )

        if idempotency_key:
            existing = await self._runs.get_by_idempotency_key(
                organization_id, idempotency_key
            )
            if existing is not None:
                return existing

        run = AgentRun(
            organization_id=organization_id,
            agent_name=agent_name,
            status=AgentRunStatus.QUEUED,
            trigger=trigger,
            workflow_id=workflow_id,
            input=input_,
            idempotency_key=idempotency_key,
        )
        self._runs.add(run)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise AppError(
                code="agent_run.duplicate_idempotency_key",
                message="An agent run with this idempotency key already exists",
                status_code=409,
            ) from exc
        await commit_with_retry(self._session)
        get_counter(
            "agent_run_queued_total",
            description="Agent runs queued for the runtime worker",
        ).add()
        return run

    async def update_run(
        self,
        organization_id: uuid.UUID,
        run_id: uuid.UUID,
        *,
        output: dict | None = None,
        error: str | None = None,
        duration_ms: int | None = None,
        cost: Decimal | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
    ) -> AgentRun:
        """Update run metadata only; never status (runtime-owned)."""
        run = await self._runs.get_or_404(organization_id, run_id)
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

    # -- runtime-owned lifecycle transitions ----------------------------

    async def start_run(
        self, organization_id: uuid.UUID, run_id: uuid.UUID
    ) -> AgentRun:
        """QUEUED -> RUNNING (worker claims the run)."""
        run = await self._runs.get_or_404(organization_id, run_id)
        assert_transition(run.status, AgentRunStatus.RUNNING)
        updated = await self._runs.mark_started(organization_id, run_id)
        if updated is None:
            await self._session.rollback()
            raise AppError(
                code="agent_run.invalid_state",
                message="Agent run was cancelled or claimed by another worker",
                status_code=409,
            )
        await commit_with_retry(self._session)
        return updated

    async def complete_run(
        self,
        organization_id: uuid.UUID,
        run_id: uuid.UUID,
        *,
        output: dict,
        cost: Decimal | None = None,
    ) -> AgentRun:
        """RUNNING -> SUCCEEDED, honouring a concurrent cancel request."""
        run = await self._runs.get_or_404(organization_id, run_id)
        assert_transition(run.status, AgentRunStatus.SUCCEEDED)
        finished_at = utcnow()
        updated = await self._runs.mark_succeeded(
            organization_id,
            run_id,
            output=output,
            cost=cost,
            finished_at=finished_at,
        )
        if updated is None:
            updated = await self._runs.mark_cancelled_after_run(
                organization_id, run_id, finished_at=finished_at
            )
        if updated is None:
            await self._session.rollback()
            raise AppError(
                code="agent_run.invalid_state",
                message="Agent run state changed concurrently",
                status_code=409,
            )
        self._finalize(updated, finished_at)
        await commit_with_retry(self._session)
        return updated

    async def fail_run(
        self,
        organization_id: uuid.UUID,
        run_id: uuid.UUID,
        *,
        error: str,
    ) -> AgentRun:
        """RUNNING -> FAILED, honouring a concurrent cancel request."""
        run = await self._runs.get_or_404(organization_id, run_id)
        assert_transition(run.status, AgentRunStatus.FAILED)
        finished_at = utcnow()
        if run.cancel_requested_at is not None:
            updated = await self._runs.mark_cancelled_after_run(
                organization_id, run_id, finished_at=finished_at
            )
        else:
            updated = await self._runs.mark_failed(
                organization_id, run_id, error=error, finished_at=finished_at
            )
        if updated is None:
            updated = await self._runs.mark_cancelled_after_run(
                organization_id, run_id, finished_at=finished_at
            )
        if updated is None:
            await self._session.rollback()
            raise AppError(
                code="agent_run.invalid_state",
                message="Agent run state changed concurrently",
                status_code=409,
            )
        self._finalize(updated, finished_at)
        await commit_with_retry(self._session)
        return updated

    async def fail_queued_run(
        self,
        organization_id: uuid.UUID,
        run_id: uuid.UUID,
        *,
        error: str,
    ) -> AgentRun:
        """QUEUED -> FAILED (agent became unavailable before dispatch)."""
        run = await self._runs.get_or_404(organization_id, run_id)
        assert_transition(run.status, AgentRunStatus.FAILED)
        finished_at = utcnow()
        updated = await self._runs.mark_failed_if_queued(
            organization_id, run_id, error=error, finished_at=finished_at
        )
        if updated is None:
            await self._session.rollback()
            raise AppError(
                code="agent_run.invalid_state",
                message="Agent run state changed concurrently",
                status_code=409,
            )
        self._finalize(updated, finished_at)
        await commit_with_retry(self._session)
        return updated

    async def cancel_run(
        self,
        organization_id: uuid.UUID,
        run_id: uuid.UUID,
        *,
        cancelled_by_user_id: uuid.UUID | None = None,
    ) -> AgentRun:
        """Cancel a run.

        QUEUED runs are transitioned to CANCELLED immediately. A RUNNING run is
        only flagged (``cancel_requested_at``): the worker honours the flag when
        the executor returns and lands on CANCELLED, so an in-flight run is
        never left half-finished or wrongly marked succeeded.
        """
        run = await self._runs.get_or_404(organization_id, run_id)
        if run.status == AgentRunStatus.CANCELLED:
            return run
        if not is_cancellable(run.status):
            raise AppError(
                code="agent_run.not_cancellable",
                message="This agent run cannot be cancelled",
                status_code=409,
            )
        finished_at = utcnow()
        updated: AgentRun | None = None
        if run.status == AgentRunStatus.QUEUED:
            updated = await self._runs.mark_cancelled_if_pending(
                organization_id,
                run_id,
                cancel_requested_at=finished_at,
                cancelled_by_user_id=cancelled_by_user_id,
                finished_at=finished_at,
            )
            if updated is None:
                updated = await self._runs.mark_cancel_requested(
                    organization_id,
                    run_id,
                    cancel_requested_at=finished_at,
                    cancelled_by_user_id=cancelled_by_user_id,
                )
        else:
            updated = await self._runs.mark_cancel_requested(
                organization_id,
                run_id,
                cancel_requested_at=finished_at,
                cancelled_by_user_id=cancelled_by_user_id,
            )
        if updated is None:
            updated = await self._runs.get_or_404(organization_id, run_id)
        if updated.status == AgentRunStatus.CANCELLED:
            get_counter(
                "agent_run_cancelled_total",
                description="Agent runs cancelled",
            ).add()
        await commit_with_retry(self._session)
        return updated

    async def apply_cancel(
        self, organization_id: uuid.UUID, run_id: uuid.UUID
    ) -> AgentRun:
        """RUNNING with a cancel flag -> CANCELLED (worker sweep)."""
        run = await self._runs.get_or_404(organization_id, run_id)
        assert_transition(run.status, AgentRunStatus.CANCELLED)
        finished_at = utcnow()
        updated = await self._runs.mark_cancelled_after_run(
            organization_id, run_id, finished_at=finished_at
        )
        if updated is None:
            await self._session.rollback()
            raise AppError(
                code="agent_run.invalid_state",
                message="Agent run state changed concurrently",
                status_code=409,
            )
        self._finalize(updated, finished_at)
        await commit_with_retry(self._session)
        return updated

    def _finalize(self, run: AgentRun, finished_at: datetime) -> None:
        """Record duration + terminal counter when the run just finished."""
        if run.started_at is not None:
            run.duration_ms = int((finished_at - run.started_at).total_seconds() * 1000)
        if run.status is AgentRunStatus.SUCCEEDED:
            get_counter(
                "agent_run_succeeded_total",
                description="Agent runs that succeeded",
            ).add()
        elif run.status is AgentRunStatus.FAILED:
            get_counter(
                "agent_run_failed_total",
                description="Agent runs that failed terminally",
            ).add()
        elif run.status is AgentRunStatus.CANCELLED:
            get_counter(
                "agent_run_cancelled_total",
                description="Agent runs cancelled",
            ).add()

    # -- worker sweep helpers -------------------------------------------

    async def get_queued(self, limit: int) -> list[AgentRun]:
        return await self._runs.get_queued(limit)

    async def get_queued_orgs(self, limit: int) -> list[uuid.UUID]:
        return await self._runs.get_queued_orgs(limit)

    async def get_queued_for_org(
        self, organization_id: uuid.UUID, limit: int
    ) -> list[AgentRun]:
        return await self._runs.get_queued_for_org(organization_id, limit)

    async def count_pending(self, organization_id: uuid.UUID) -> int:
        return await self._runs.count_pending(organization_id)

    async def get_cancel_requested(self, limit: int) -> list[AgentRun]:
        return await self._runs.get_cancel_requested(limit)

    async def get_stuck_running(self) -> list[AgentRun]:
        return await self._runs.get_stuck_running()

    # -- agent state -----------------------------------------------------

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
