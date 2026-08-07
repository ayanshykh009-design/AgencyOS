"""AgentState repository (per-agent health bookkeeping).

The runtime upserts one row per (organization, agent_name).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, cast

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_state import AgentState
from app.models.enums import AgentHealth, AgentStateStatus
from app.repositories.base import TenantRepository

if TYPE_CHECKING:
    pass


class AgentStateRepository(TenantRepository[AgentState]):
    """Data access for per-agent health rows (org-scoped)."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, AgentState)

    async def upsert(
        self,
        *,
        organization_id: uuid.UUID,
        agent_name: str,
        status: AgentStateStatus,
        health: AgentHealth,
        queue_depth: int,
        total_runs: int,
        average_runtime_ms: Decimal,
        average_cost: Decimal,
        last_execution: datetime | None,
        last_error: str | None,
    ) -> None:
        """Insert or update the single state row for (org, agent)."""
        values = {
            "organization_id": organization_id,
            "agent_name": agent_name,
            "status": status,
            "health": health,
            "queue_depth": queue_depth,
            "total_runs": total_runs,
            "average_runtime_ms": average_runtime_ms,
            "average_cost": average_cost,
            "last_execution": last_execution,
            "last_error": last_error,
        }
        stmt = insert(AgentState).values(**values)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_agent_state_org_agent",
            set_={
                "status": status,
                "health": health,
                "queue_depth": queue_depth,
                "total_runs": total_runs,
                "average_runtime_ms": average_runtime_ms,
                "average_cost": average_cost,
                "last_execution": last_execution,
                "last_error": last_error,
            },
        )
        await self._session.execute(stmt)

    async def list_by_status(
        self,
        organization_id: uuid.UUID,
        *,
        status: AgentStateStatus | None = None,
        limit: int = 100,
    ) -> list[AgentState]:
        """List agent states, optionally filtered by status."""
        stmt = select(AgentState).where(
            AgentState.organization_id == organization_id
        )
        if status is not None:
            stmt = stmt.where(AgentState.status == status)
        stmt = stmt.order_by(AgentState.agent_name).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def mark_heartbeat(
        self,
        organization_id: uuid.UUID,
        agent_name: str,
        *,
        last_execution: datetime,
    ) -> int:
        """Touch ``last_execution`` for an agent; returns rows updated."""
        stmt = (
            update(AgentState)
            .where(
                AgentState.organization_id == organization_id,
                AgentState.agent_name == agent_name,
            )
            .values(last_execution=last_execution)
        )
        result = cast(CursorResult, await self._session.execute(stmt))
        return result.rowcount or 0
