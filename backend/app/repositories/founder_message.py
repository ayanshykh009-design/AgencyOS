"""Founder message repository (org-scoped conversation turns)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.founder_message import FounderMessage
from app.repositories.base import TenantRepository


class FounderMessageRepository(TenantRepository[FounderMessage]):
    """Data access for founder messages (org-scoped)."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, FounderMessage)

    async def list_by_conversation(
        self,
        organization_id: uuid.UUID,
        conversation_id: uuid.UUID,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> list[FounderMessage]:
        """Return messages for a conversation, oldest first (chronological)."""
        stmt = (
            select(FounderMessage)
            .where(
                FounderMessage.organization_id == organization_id,
                FounderMessage.conversation_id == conversation_id,
            )
            .order_by(FounderMessage.sent_at.asc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_conversation(
        self, organization_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> int:
        """Count messages in a conversation (within the org)."""
        from sqlalchemy import func

        stmt = (
            select(func.count(FounderMessage.id))
            .where(
                FounderMessage.organization_id == organization_id,
                FounderMessage.conversation_id == conversation_id,
            )
            .select_from(FounderMessage)
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())
