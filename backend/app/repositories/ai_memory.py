"""AiMemory repository (working + long-term memory store).

Working memories are ephemeral: ``delete_working_older_than`` supports the
retention sweep bounded by ``MEMORY_WORKING_TTL_DAYS``. Long-term memories
are durable and never pruned here.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, cast

from sqlalchemy import delete, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_memory import AiMemory
from app.models.enums import MemoryScope, MemoryType
from app.repositories.base import TenantRepository

if TYPE_CHECKING:
    pass


class AiMemoryRepository(TenantRepository[AiMemory]):
    """Data access for AI memory rows (org-scoped)."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, AiMemory)

    async def list_by_scope(
        self,
        organization_id: uuid.UUID,
        *,
        memory_type: MemoryType | None = None,
        scope: MemoryScope | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AiMemory]:
        """List memories, optionally filtered by type/scope, newest first."""
        stmt = select(AiMemory).where(AiMemory.organization_id == organization_id)
        if memory_type is not None:
            stmt = stmt.where(AiMemory.memory_type == memory_type)
        if scope is not None:
            stmt = stmt.where(AiMemory.scope == scope)
        stmt = stmt.order_by(AiMemory.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def delete_working_older_than(self, cutoff: datetime, batch: int) -> int:
        """Prune at most ``batch`` working memories older than ``cutoff``.

        Retention sweep support; bounded by ``batch`` to avoid long locks.
        Long-term memories are never deleted here.
        """
        subq = (
            select(AiMemory.id)
            .where(
                AiMemory.memory_type == MemoryType.WORKING,
                AiMemory.created_at < cutoff,
            )
            .order_by(AiMemory.created_at)
            .limit(max(batch, 1))
        )
        stmt = delete(AiMemory).where(AiMemory.id.in_(subq))
        result = cast(CursorResult, await self._session.execute(stmt))
        return result.rowcount or 0
