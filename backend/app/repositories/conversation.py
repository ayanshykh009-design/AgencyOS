"""Conversation repositories: threads and thread messages."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.conversation import Conversation
from app.models.conversation_message import ConversationMessage


class ConversationRepository:
    """Data access for conversation threads."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self, organization_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> Conversation | None:
        conversation = await self._session.get(Conversation, conversation_id)
        if conversation is None or conversation.organization_id != organization_id:
            return None
        return conversation

    async def get_or_404(
        self, organization_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> Conversation:
        conversation = await self.get(organization_id, conversation_id)
        if conversation is None:
            raise AppError(
                code="conversation.not_found",
                message="Conversation not found",
                status_code=404,
            )
        return conversation

    async def list_for_lead(
        self, organization_id: uuid.UUID, lead_id: uuid.UUID
    ) -> list[Conversation]:
        stmt = (
            select(Conversation)
            .where(
                Conversation.organization_id == organization_id,
                Conversation.lead_id == lead_id,
            )
            .order_by(Conversation.updated_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_open(
        self,
        organization_id: uuid.UUID,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Conversation]:
        stmt = (
            select(Conversation)
            .where(
                Conversation.organization_id == organization_id,
                Conversation.is_open.is_(True),
            )
            .order_by(Conversation.last_message_at.desc().nullslast())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_open(self, organization_id: uuid.UUID) -> int:
        stmt = (
            select(Conversation.id)
            .where(
                Conversation.organization_id == organization_id,
                Conversation.is_open.is_(True),
            )
            .select_from(Conversation)
        )
        result = await self._session.execute(stmt)
        return len(result.all())

    def add(self, conversation: Conversation) -> None:
        self._session.add(conversation)


class ConversationMessageRepository:
    """Data access for messages inside a conversation thread."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_conversation(
        self,
        organization_id: uuid.UUID,
        conversation_id: uuid.UUID,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> list[ConversationMessage]:
        stmt = (
            select(ConversationMessage)
            .where(
                ConversationMessage.organization_id == organization_id,
                ConversationMessage.conversation_id == conversation_id,
            )
            .order_by(ConversationMessage.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    def add(self, message: ConversationMessage) -> None:
        self._session.add(message)
