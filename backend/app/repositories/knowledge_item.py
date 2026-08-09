"""KnowledgeItem repository (durable long-term knowledge)."""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_item import KnowledgeItem
from app.repositories.base import TenantRepository

if TYPE_CHECKING:
    pass


class KnowledgeItemRepository(TenantRepository[KnowledgeItem]):
    """Data access for knowledge items (org-scoped)."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, KnowledgeItem)

    async def list_by_category(
        self,
        organization_id: uuid.UUID,
        *,
        category: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[KnowledgeItem]:
        """List knowledge, optionally filtered by category, newest first."""
        stmt = select(KnowledgeItem).where(
            KnowledgeItem.organization_id == organization_id
        )
        if category is not None:
            stmt = stmt.where(KnowledgeItem.category == category)
        stmt = stmt.order_by(KnowledgeItem.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def search(
        self,
        organization_id: uuid.UUID,
        *,
        query: str,
        limit: int = 50,
    ) -> list[KnowledgeItem]:
        """Substring search over knowledge title/content, org-scoped."""
        like = f"%{query}%"
        stmt = (
            select(KnowledgeItem)
            .where(
                KnowledgeItem.organization_id == organization_id,
                (KnowledgeItem.title.ilike(like))
                | (KnowledgeItem.content.ilike(like)),
            )
            .order_by(KnowledgeItem.created_at.desc())
            .limit(min(limit, 200))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_source_memory(
        self,
        organization_id: uuid.UUID,
        memory_id: uuid.UUID,
    ) -> KnowledgeItem | None:
        """Return the knowledge item promoted from a given working memory.

        Promotion is service-internal and 1:1; this lookup (scoped by
        ``organization_id`` plus the ``source_memory_id`` FK) is the duplicate
        guard used by ``promote_to_knowledge``.
        """
        stmt = select(KnowledgeItem).where(
            KnowledgeItem.organization_id == organization_id,
            KnowledgeItem.source_memory_id == memory_id,
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def count_by_category(self, organization_id: uuid.UUID) -> dict[str, int]:
        """Knowledge counts grouped by category."""
        stmt = (
            select(KnowledgeItem.category, func.count(KnowledgeItem.id))
            .where(KnowledgeItem.organization_id == organization_id)
            .group_by(KnowledgeItem.category)
        )
        result = await self._session.execute(stmt)
        return {category: int(count) for category, count in result.all()}
