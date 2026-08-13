"""AiMemory repository (working + long-term memory store).

Working memories are ephemeral: ``delete_working_older_than`` supports the
retention sweep bounded by ``MEMORY_WORKING_TTL_DAYS``. Long-term memories
are durable and never pruned here.

M4 adds the org-scoped primitives used by the memory TTL worker and the
retrieval pipeline: ``find_duplicate``, ``list_expired_working``,
``delete_many``, and ``list_ranked``. Every query is scoped by
``organization_id`` (defense in depth behind RLS) and reuses the existing
indexes (``idx_ai_memories_org_type``, ``idx_ai_memories_org_created``,
``idx_ai_memories_working_ttl``).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast

from sqlalchemy import delete, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.classification import normalize_content
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

    async def find_duplicate(
        self,
        organization_id: uuid.UUID,
        normalized_content: str,
        ttl_window: timedelta,
    ) -> AiMemory | None:
        """Return the newest working memory with identical normalized content.

        Scoped to ``organization_id`` and to rows created within
        ``ttl_window`` (the write-time dedup horizon). ``normalized_content``
        must already be the output of :func:`normalize_content`; candidate rows
        are normalized in-process so the original stored content is untouched.
        """
        cutoff = datetime.now(UTC) - ttl_window
        stmt = (
            select(AiMemory)
            .where(
                AiMemory.organization_id == organization_id,
                AiMemory.memory_type == MemoryType.WORKING,
                AiMemory.created_at >= cutoff,
            )
            .order_by(AiMemory.created_at.desc())
            .limit(100)
        )
        result = await self._session.execute(stmt)
        for memory in result.scalars().all():
            if normalize_content(memory.content) == normalized_content:
                return memory
        return None

    async def list_expired_working(
        self,
        organization_id: uuid.UUID,
        before: datetime,
        batch: int,
    ) -> list[AiMemory]:
        """Return up to ``batch`` expired working memories, oldest first.

        Org-scoped; only ``memory_type='working'`` rows older than ``before``
        are eligible. Long-term memories are never returned here.
        """
        stmt = (
            select(AiMemory)
            .where(
                AiMemory.organization_id == organization_id,
                AiMemory.memory_type == MemoryType.WORKING,
                AiMemory.created_at < before,
            )
            .order_by(AiMemory.created_at)
            .limit(max(batch, 1))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def delete_many(
        self,
        organization_id: uuid.UUID,
        ids: list[uuid.UUID],
    ) -> int:
        """Delete the given memory ids within one organization.

        Org-scoped by construction: ids that do not belong to
        ``organization_id`` are never deleted. Returns the number deleted.
        """
        if not ids:
            return 0
        stmt = delete(AiMemory).where(
            AiMemory.organization_id == organization_id,
            AiMemory.id.in_(ids),
        )
        result = cast(CursorResult, await self._session.execute(stmt))
        return result.rowcount or 0

    async def list_ranked(
        self,
        organization_id: uuid.UUID,
        *,
        scope: MemoryScope | None = None,
        limit: int = 100,
    ) -> list[AiMemory]:
        """Return org-scoped candidate memories, newest first, bounded.

        The bounded candidate pool is ranked in the scoring layer
        (``app.memory.scoring``); this repository primitive only narrows the
        candidate set deterministically and reuses ``idx_ai_memories_org_created``.
        """
        stmt = select(AiMemory).where(AiMemory.organization_id == organization_id)
        if scope is not None:
            stmt = stmt.where(AiMemory.scope == scope)
        stmt = stmt.order_by(AiMemory.created_at.desc()).limit(max(limit, 1))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
