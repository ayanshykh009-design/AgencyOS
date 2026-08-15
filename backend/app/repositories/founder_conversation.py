"""Founder conversation repository (org-scoped chat threads)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.founder_conversation import FounderConversation
from app.repositories.base import TenantRepository

if TYPE_CHECKING:
    pass


class FounderConversationRepository(TenantRepository[FounderConversation]):
    """Data access for founder conversations (org-scoped)."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, FounderConversation)

    async def list_for_org(
        self,
        organization_id: uuid.UUID,
        *,
        limit: int = 50,
        offset: int = 0,
        include_archived: bool = False,
    ) -> list[FounderConversation]:
        """List conversations, newest activity first; archived excluded by default."""
        stmt = select(FounderConversation).where(
            FounderConversation.organization_id == organization_id
        )
        if not include_archived:
            stmt = stmt.where(FounderConversation.is_archived.is_(False))
        stmt = stmt.order_by(FounderConversation.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def set_archived(
        self, organization_id: uuid.UUID, conversation_id: uuid.UUID, *, archived: bool
    ) -> bool:
        """Archive / un-archive a conversation within the org; returns False if missing."""
        conversation = await self.get(organization_id, conversation_id)
        if conversation is None:
            return False
        conversation.is_archived = archived
        return True

    async def touch(self, conversation: FounderConversation, *, when: datetime) -> None:
        """Update ``last_message_at`` to ``when`` (caller commits)."""
        conversation.last_message_at = when
