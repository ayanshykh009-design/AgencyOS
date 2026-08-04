"""WorkflowEvent repository (append-only event log)."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow_event import WorkflowEvent

if TYPE_CHECKING:
    pass


_DEFAULT_PAGE_SIZE = 50
_MAX_PAGE_SIZE = 200

# Module-level alias so ``list[...]`` annotations inside the class (which has a
# ``list`` method) resolve to the builtin type, not the shadowing method.
WorkflowEventList = list[WorkflowEvent]


class WorkflowEventRepository:
    """Data access for workflow events."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, organization_id: uuid.UUID, event_id: uuid.UUID) -> WorkflowEvent | None:
        stmt = select(WorkflowEvent).where(
            WorkflowEvent.organization_id == organization_id,
            WorkflowEvent.id == event_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_org(
        self,
        organization_id: uuid.UUID,
        *,
        event_type: str | None = None,
        consumed: bool | None = None,
        sort: str = "occurred_at",
        order: str = "desc",
        limit: int = _DEFAULT_PAGE_SIZE,
        offset: int = 0,
    ) -> list[WorkflowEvent]:
        stmt = select(WorkflowEvent).where(WorkflowEvent.organization_id == organization_id)
        if event_type is not None:
            stmt = stmt.where(WorkflowEvent.event_type == event_type)
        if consumed is not None:
            stmt = stmt.where(WorkflowEvent.consumed == consumed)

        sort_col = getattr(WorkflowEvent, sort, WorkflowEvent.occurred_at)
        if order == "desc":
            sort_col = sort_col.desc()
        stmt = stmt.order_by(sort_col).limit(min(limit, _MAX_PAGE_SIZE)).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_org(
        self,
        organization_id: uuid.UUID,
        *,
        event_type: str | None = None,
        consumed: bool | None = None,
    ) -> int:
        stmt = (
            select(func.count(WorkflowEvent.id))
            .where(WorkflowEvent.organization_id == organization_id)
            .select_from(WorkflowEvent)
        )
        if event_type is not None:
            stmt = stmt.where(WorkflowEvent.event_type == event_type)
        if consumed is not None:
            stmt = stmt.where(WorkflowEvent.consumed == consumed)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    def add(self, event: WorkflowEvent) -> None:
        self._session.add(event)

    async def flush(self) -> None:
        await self._session.flush()

    async def refresh(self, event: WorkflowEvent) -> None:
        await self._session.refresh(event)

    async def mark_consumed(
        self, organization_id: uuid.UUID, event_ids: list[uuid.UUID]
    ) -> int:
        """Mark a batch of unconsumed events as consumed. Returns rows updated."""
        stmt = (
            update(WorkflowEvent)
            .where(
                WorkflowEvent.organization_id == organization_id,
                WorkflowEvent.id.in_(event_ids),
                WorkflowEvent.consumed.is_(False),
            )
            .values(consumed=True, consumed_at=datetime.now(UTC))
        )
        result = cast(CursorResult, await self._session.execute(stmt))
        return result.rowcount or 0

    async def get_unconsumed_by_type(
        self, organization_id: uuid.UUID, event_type: str
    ) -> WorkflowEventList:
        stmt = select(WorkflowEvent).where(
            WorkflowEvent.organization_id == organization_id,
            WorkflowEvent.event_type == event_type,
            WorkflowEvent.consumed.is_(False),
        ).order_by(WorkflowEvent.occurred_at)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())