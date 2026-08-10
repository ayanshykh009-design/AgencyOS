"""AgentRun repository (per-run execution records).

Rows are pruned after ``AGENT_RUN_RETENTION_DAYS`` by the retention sweep on
``created_at``. All state transitions are guarded single conditional
``UPDATE ... RETURNING`` statements (mirroring ``WorkflowExecutionRepository``)
so a concurrent worker and a cancel can never clobber each other: the row-level
WHERE is re-evaluated against the latest committed row.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast

from sqlalchemy import delete, func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_run import AgentRun
from app.models.enums import AgentRunStatus
from app.repositories.base import TenantRepository

if TYPE_CHECKING:
    pass


class AgentRunRepository(TenantRepository[AgentRun]):
    """Data access for agent run records (org-scoped)."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, AgentRun)

    async def list_by_agent(
        self,
        organization_id: uuid.UUID,
        agent_name: str,
        *,
        status: AgentRunStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AgentRun]:
        """List runs for one agent, newest first, optionally by status."""
        stmt = select(AgentRun).where(
            AgentRun.organization_id == organization_id,
            AgentRun.agent_name == agent_name,
        )
        if status is not None:
            stmt = stmt.where(AgentRun.status == status)
        stmt = stmt.order_by(AgentRun.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_idempotency_key(
        self, organization_id: uuid.UUID, idempotency_key: str
    ) -> AgentRun | None:
        """Return the existing run for (org, key), or None."""
        stmt = select(AgentRun).where(
            AgentRun.organization_id == organization_id,
            AgentRun.idempotency_key == idempotency_key,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_older_than(self, cutoff: datetime, batch: int) -> int:
        """Prune at most ``batch`` runs older than ``cutoff`` (retention)."""
        subq = (
            select(AgentRun.id)
            .where(AgentRun.created_at < cutoff)
            .order_by(AgentRun.created_at)
            .limit(max(batch, 1))
        )
        stmt = delete(AgentRun).where(AgentRun.id.in_(subq))
        result = cast(CursorResult, await self._session.execute(stmt))
        return result.rowcount or 0

    # Queue operations ---------------------------------------------------------

    async def get_queued(self, limit: int) -> list[AgentRun]:
        """Get QUEUED runs across all organizations (worker drain)."""
        stmt = (
            select(AgentRun)
            .where(AgentRun.status == AgentRunStatus.QUEUED)
            .order_by(AgentRun.created_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_queued_orgs(self, limit: int) -> list[uuid.UUID]:
        """Fair-drain candidates: orgs with QUEUED work, oldest-first.

        ``GROUP BY organization_id ORDER BY MIN(created_at)`` guarantees an org
        that has been waiting longest is visited first, so one busy org cannot
        starve everyone else's queue.
        """
        stmt = (
            select(AgentRun.organization_id)
            .where(AgentRun.status == AgentRunStatus.QUEUED)
            .group_by(AgentRun.organization_id)
            .order_by(func.min(AgentRun.created_at))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_queued_for_org(
        self, organization_id: uuid.UUID, limit: int
    ) -> list[AgentRun]:
        """Get the oldest QUEUED runs for one organization."""
        stmt = (
            select(AgentRun)
            .where(
                AgentRun.organization_id == organization_id,
                AgentRun.status == AgentRunStatus.QUEUED,
            )
            .order_by(AgentRun.created_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_pending(self, organization_id: uuid.UUID) -> int:
        """Count QUEUED runs for one organization (queue-depth bookkeeping)."""
        stmt = (
            select(func.count(AgentRun.id))
            .where(
                AgentRun.organization_id == organization_id,
                AgentRun.status == AgentRunStatus.QUEUED,
            )
            .select_from(AgentRun)
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def count_pending_all_orgs(self) -> int:
        """Count QUEUED runs across all organizations."""
        stmt = (
            select(func.count(AgentRun.id))
            .where(AgentRun.status == AgentRunStatus.QUEUED)
            .select_from(AgentRun)
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def count_status(self, status: AgentRunStatus) -> int:
        """Count runs in a given status across all organizations."""
        stmt = (
            select(func.count(AgentRun.id))
            .where(AgentRun.status == status)
            .select_from(AgentRun)
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def get_cancel_requested(self, limit: int) -> list[AgentRun]:
        """RUNNING runs flagged for cancellation (in-flight cancel sweep)."""
        stmt = (
            select(AgentRun)
            .where(
                AgentRun.status == AgentRunStatus.RUNNING,
                AgentRun.cancel_requested_at.is_not(None),
            )
            .order_by(AgentRun.cancel_requested_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_stuck_running(self, before: datetime | None = None) -> list[AgentRun]:
        """RUNNING runs that have exceeded the timeout (stale re-convergence).

        Agent runs have no separate ``timed_out`` status: a stuck run is
        re-converged by failing it with a timeout error. ``before`` is the
        ``started_at`` cutoff; ``AGENT_RUN_TIMEOUT_SECONDS`` computes it.
        """
        from app.core.config import settings

        cutoff = before or (
            datetime.now(UTC) - timedelta(seconds=settings.AGENT_RUN_TIMEOUT_SECONDS)
        )
        stmt = select(AgentRun).where(
            AgentRun.status == AgentRunStatus.RUNNING,
            AgentRun.started_at.is_not(None),
            AgentRun.started_at < cutoff,
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    # Guarded state transitions -------------------------------------------------
    #
    # Every transition is a single conditional UPDATE .. RETURNING so the
    # row-level WHERE is re-evaluated against the latest committed row. A
    # concurrent worker or cancel can never clobber a transition; callers
    # receive the updated row or ``None``.

    async def mark_started(
        self, organization_id: uuid.UUID, run_id: uuid.UUID
    ) -> AgentRun | None:
        """QUEUED + no cancel flag -> RUNNING. Returns row or None."""
        stmt = (
            update(AgentRun)
            .where(
                AgentRun.organization_id == organization_id,
                AgentRun.id == run_id,
                AgentRun.status == AgentRunStatus.QUEUED,
                AgentRun.cancel_requested_at.is_(None),
            )
            .values(status=AgentRunStatus.RUNNING, started_at=func.now())
            .returning(AgentRun)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_succeeded(
        self,
        organization_id: uuid.UUID,
        run_id: uuid.UUID,
        *,
        output: dict,
        cost: object | None = None,
        finished_at: datetime,
    ) -> AgentRun | None:
        """RUNNING + no cancel flag -> SUCCEEDED. Returns row or None."""
        values: dict = {"status": AgentRunStatus.SUCCEEDED, "finished_at": finished_at}
        if output is not None:
            values["output"] = output
        if cost is not None:
            values["cost"] = cost
        stmt = (
            update(AgentRun)
            .where(
                AgentRun.organization_id == organization_id,
                AgentRun.id == run_id,
                AgentRun.status == AgentRunStatus.RUNNING,
                AgentRun.cancel_requested_at.is_(None),
            )
            .values(**values)
            .returning(AgentRun)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_failed(
        self,
        organization_id: uuid.UUID,
        run_id: uuid.UUID,
        *,
        error: str,
        finished_at: datetime,
    ) -> AgentRun | None:
        """RUNNING + no cancel flag -> FAILED. Returns row or None."""
        stmt = (
            update(AgentRun)
            .where(
                AgentRun.organization_id == organization_id,
                AgentRun.id == run_id,
                AgentRun.status == AgentRunStatus.RUNNING,
                AgentRun.cancel_requested_at.is_(None),
            )
            .values(
                status=AgentRunStatus.FAILED,
                error=error,
                finished_at=finished_at,
            )
            .returning(AgentRun)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_failed_if_queued(
        self,
        organization_id: uuid.UUID,
        run_id: uuid.UUID,
        *,
        error: str,
        finished_at: datetime,
    ) -> AgentRun | None:
        """QUEUED -> FAILED (agent became unavailable before dispatch)."""
        stmt = (
            update(AgentRun)
            .where(
                AgentRun.organization_id == organization_id,
                AgentRun.id == run_id,
                AgentRun.status == AgentRunStatus.QUEUED,
            )
            .values(
                status=AgentRunStatus.FAILED,
                error=error,
                finished_at=finished_at,
            )
            .returning(AgentRun)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_cancelled_after_run(
        self,
        organization_id: uuid.UUID,
        run_id: uuid.UUID,
        *,
        finished_at: datetime,
    ) -> AgentRun | None:
        """RUNNING with a cancel flag -> CANCELLED. Returns row or None."""
        stmt = (
            update(AgentRun)
            .where(
                AgentRun.organization_id == organization_id,
                AgentRun.id == run_id,
                AgentRun.status == AgentRunStatus.RUNNING,
                AgentRun.cancel_requested_at.is_not(None),
            )
            .values(status=AgentRunStatus.CANCELLED, finished_at=finished_at)
            .returning(AgentRun)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_cancelled_if_pending(
        self,
        organization_id: uuid.UUID,
        run_id: uuid.UUID,
        *,
        cancel_requested_at: datetime,
        cancelled_by_user_id: uuid.UUID | None,
        finished_at: datetime,
    ) -> AgentRun | None:
        """QUEUED + no cancel flag -> CANCELLED. Returns row or None."""
        stmt = (
            update(AgentRun)
            .where(
                AgentRun.organization_id == organization_id,
                AgentRun.id == run_id,
                AgentRun.status == AgentRunStatus.QUEUED,
                AgentRun.cancel_requested_at.is_(None),
            )
            .values(
                status=AgentRunStatus.CANCELLED,
                cancel_requested_at=cancel_requested_at,
                cancelled_by_user_id=cancelled_by_user_id,
                finished_at=finished_at,
            )
            .returning(AgentRun)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_cancel_requested(
        self,
        organization_id: uuid.UUID,
        run_id: uuid.UUID,
        *,
        cancel_requested_at: datetime,
        cancelled_by_user_id: uuid.UUID | None,
    ) -> AgentRun | None:
        """RUNNING + no cancel flag: flag the row for in-flight cancellation."""
        stmt = (
            update(AgentRun)
            .where(
                AgentRun.organization_id == organization_id,
                AgentRun.id == run_id,
                AgentRun.status == AgentRunStatus.RUNNING,
                AgentRun.cancel_requested_at.is_(None),
            )
            .values(
                cancel_requested_at=cancel_requested_at,
                cancelled_by_user_id=cancelled_by_user_id,
            )
            .returning(AgentRun)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
