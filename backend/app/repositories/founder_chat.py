"""Founder chat read-side counts (org-scoped).

Pagination totals must come from a ``COUNT`` over the same filters as the
page query. The listing itself lives in :class:`FounderConversationRepository`;
this repository deliberately mirrors only its filter set so callers can ask
for the true filtered total without loading every row.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.founder_conversation import FounderConversation
from app.repositories.base import TenantRepository


class FounderChatRepository(TenantRepository[FounderConversation]):
    """Count queries backing the founder chat list endpoints."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, FounderConversation)

    async def count_conversations(
        self,
        organization_id: uuid.UUID,
        *,
        include_archived: bool = False,
    ) -> int:
        """Count conversations with ``list_for_org``'s org/archive filters."""
        stmt = select(func.count(FounderConversation.id)).where(
            FounderConversation.organization_id == organization_id
        )
        if not include_archived:
            stmt = stmt.where(FounderConversation.is_archived.is_(False))
        result = await self._session.execute(stmt.select_from(FounderConversation))
        return int(result.scalar_one())
