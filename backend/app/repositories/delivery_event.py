"""DeliveryEventRepository — immutable per-delivery timeline (append-only)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import cast

from sqlalchemy import delete, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.delivery_event import DeliveryEvent
from app.repositories.base import TenantRepository

DeliveryEventList = list[DeliveryEvent]


class DeliveryEventRepository(TenantRepository[DeliveryEvent]):
    """Data access for the append-only delivery timeline."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, DeliveryEvent)

    async def list_by_delivery(
        self,
        organization_id: uuid.UUID,
        delivery_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> DeliveryEventList:
        """Timeline for one delivery, oldest first."""
        stmt = (
            select(DeliveryEvent)
            .where(
                DeliveryEvent.organization_id == organization_id,
                DeliveryEvent.delivery_id == delivery_id,
            )
            .order_by(DeliveryEvent.occurred_at)
            .limit(min(limit, 200))
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def delete_older_than(self, cutoff: datetime, limit: int) -> int:
        """Delete up to ``limit`` events older than ``cutoff`` (retention).

        Rows are never touched by feature code; only the retention sweep prunes
        them. Chunked so the delete stays bounded per statement.
        """
        subq = (
            select(DeliveryEvent.id)
            .where(DeliveryEvent.occurred_at < cutoff)
            .order_by(DeliveryEvent.occurred_at)
            .limit(limit)
        )
        stmt = delete(DeliveryEvent).where(DeliveryEvent.id.in_(subq))
        result = cast(CursorResult, await self._session.execute(stmt))
        return result.rowcount or 0
