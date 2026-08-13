"""ExecutionEvent repository (append-only execution timeline)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import cast

from sqlalchemy import delete, func, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.execution_event import ExecutionEvent


class ExecutionEventRepository:
    """Data access for execution timeline events (append + pageable query)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, event: ExecutionEvent) -> None:
        self._session.add(event)

    def add_all(self, events: list[ExecutionEvent]) -> None:
        self._session.add_all(events)

    async def flush(self) -> None:
        await self._session.flush()

    async def list_by_execution(
        self,
        organization_id: uuid.UUID,
        execution_id: uuid.UUID,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ExecutionEvent]:
        """Return the timeline for one execution, oldest first."""
        stmt = (
            select(ExecutionEvent)
            .where(
                ExecutionEvent.organization_id == organization_id,
                ExecutionEvent.execution_id == execution_id,
            )
            .order_by(ExecutionEvent.occurred_at.asc())
            .limit(min(limit, 200))
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_execution(self, organization_id: uuid.UUID, execution_id: uuid.UUID) -> int:
        stmt = (
            select(func.count(ExecutionEvent.id))
            .where(
                ExecutionEvent.organization_id == organization_id,
                ExecutionEvent.execution_id == execution_id,
            )
            .select_from(ExecutionEvent)
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def count_by_date_range(self, cutoff: datetime) -> int:
        """Count events occurred at/after ``cutoff`` across all organizations."""
        stmt = (
            select(func.count(ExecutionEvent.id))
            .where(ExecutionEvent.occurred_at >= cutoff)
            .select_from(ExecutionEvent)
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def delete_older_than(self, cutoff: datetime, batch: int) -> int:
        """Delete at most ``batch`` events older than ``cutoff`` (retention).

        Bounded by ``batch`` so the retention sweep never holds a long lock.
        Returns the number of rows deleted.
        """
        subq = (
            select(ExecutionEvent.id)
            .where(ExecutionEvent.occurred_at < cutoff)
            .order_by(ExecutionEvent.occurred_at)
            .limit(max(batch, 1))
        )
        stmt = delete(ExecutionEvent).where(ExecutionEvent.id.in_(subq))
        result = cast(CursorResult, await self._session.execute(stmt))
        return result.rowcount or 0
