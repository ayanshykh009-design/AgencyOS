"""Conversation service: threads and thread messages."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.conversation_message import ConversationMessage
from app.models.enums import ConversationSender, OutreachChannel
from app.repositories.conversation import (
    ConversationMessageRepository,
    ConversationRepository,
)
from app.services.base import commit_with_retry, utcnow


class ConversationService:
    """Owns conversation rules and the transaction boundary."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._conversations = ConversationRepository(session)
        self._messages = ConversationMessageRepository(session)

    # -- threads --------------------------------------------------------

    async def get(self, organization_id: uuid.UUID, conversation_id: uuid.UUID) -> Conversation:
        return await self._conversations.get_or_404(organization_id, conversation_id)

    async def list_for_lead(
        self, organization_id: uuid.UUID, lead_id: uuid.UUID
    ) -> list[Conversation]:
        return await self._conversations.list_for_lead(organization_id, lead_id)

    async def list_open(
        self, organization_id: uuid.UUID, *, limit: int = 50, offset: int = 0
    ) -> list[Conversation]:
        return await self._conversations.list_open(organization_id, limit=limit, offset=offset)

    async def count_open(self, organization_id: uuid.UUID) -> int:
        return await self._conversations.count_open(organization_id)

    async def create(self, organization_id: uuid.UUID, data: dict[str, Any]) -> Conversation:
        conversation = Conversation(
            organization_id=organization_id,
            lead_id=data["lead_id"],
            channel=OutreachChannel(data["channel"]),
            external_thread_id=data.get("external_thread_id"),
            subject=data.get("subject"),
            is_open=bool(data.get("is_open", True)),
        )
        self._conversations.add(conversation)
        await commit_with_retry(self._session)
        return conversation

    async def update(
        self,
        organization_id: uuid.UUID,
        conversation_id: uuid.UUID,
        data: dict[str, Any],
    ) -> Conversation:
        conversation = await self._conversations.get_or_404(organization_id, conversation_id)
        for field in ("subject", "is_open", "last_message_at"):
            if field in data:
                setattr(conversation, field, data[field])
        await commit_with_retry(self._session)
        return conversation

    # -- messages -------------------------------------------------------

    async def list_messages(
        self,
        organization_id: uuid.UUID,
        conversation_id: uuid.UUID,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> list[ConversationMessage]:
        await self._conversations.get_or_404(organization_id, conversation_id)
        return await self._messages.list_for_conversation(
            organization_id, conversation_id, limit=limit, offset=offset
        )

    async def add_message(
        self,
        organization_id: uuid.UUID,
        conversation_id: uuid.UUID,
        data: dict[str, Any],
    ) -> ConversationMessage:
        conversation = await self._conversations.get_or_404(organization_id, conversation_id)
        sender = ConversationSender(data["sender_type"])
        message = ConversationMessage(
            conversation_id=conversation_id,
            organization_id=organization_id,
            sender_type=sender,
            sender_user_id=data.get("sender_user_id"),
            body=data["body"],
            external_id=data.get("external_id"),
            metadata=data.get("metadata", {}),
            sent_at=data.get("sent_at"),
        )
        self._messages.add(message)
        conversation.last_message_at = message.sent_at or utcnow()
        if sender is ConversationSender.LEAD and not conversation.is_open:
            conversation.is_open = True
        await commit_with_retry(self._session)
        return message
