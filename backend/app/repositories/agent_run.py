"""AgentRun repository (per-run execution records).

Rows are pruned after ``AGENT_RUN_RETENTION_DAYS`` by the retention sweep on
``created_at``.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, cast

from sqlalchemy import delete, select
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
