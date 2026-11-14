"""Conversation service: threads and thread messages."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.conversation import Conversation
from app.models.conversation_message import ConversationMessage
from app.models.enums import ConversationSender, OutreachChannel
from app.models.user import User
from app.repositories.conversation import (
    ConversationMessageRepository,
    ConversationRepository,
)
from app.repositories.lead import LeadRepository
from app.services.base import commit_with_retry, utcnow


def _resolve_sent_at(value: Any) -> datetime:
    """Resolve the message timestamp, server-authoritative.

    A provider timestamp is honored only when it is an ISO-8601 string or an
    explicitly timezone-aware datetime; naive or unparseable values are
    rejected instead of being silently reinterpreted.
    """
    if value is None:
        return utcnow()
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            raise AppError(
                code="conversation.invalid_timestamp",
                message="sent_at must be an ISO 8601 timestamp",
                status_code=422,
            ) from None
    if not isinstance(value, datetime):
        raise AppError(
            code="conversation.invalid_timestamp",
            message="sent_at must be an ISO 8601 timestamp",
            status_code=422,
        )
    if value.tzinfo is None or value.utcoffset() is None:
        raise AppError(
            code="conversation.naive_timestamp",
            message="sent_at must include a timezone offset",
            status_code=422,
        )
    return value


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
        lead = await LeadRepository(self._session).get(organization_id, data["lead_id"])
        if lead is None:
            raise AppError(
                code="conversation.lead_not_found",
                message="Lead not found",
                status_code=404,
            )
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
        for field in ("subject", "is_open"):
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
        *,
        actor: User,
    ) -> ConversationMessage:
        if actor is None or getattr(actor, "id", None) is None:
            raise AppError(
                code="conversation.actor_required",
                message="Agent messages require an authenticated actor",
                status_code=422,
            )
        conversation = await self._conversations.get_or_404(organization_id, conversation_id)
        try:
            requested_sender = ConversationSender(data["sender_type"])
        except ValueError:
            raise AppError(
                code="conversation.invalid_sender",
                message="Unknown sender type",
                status_code=422,
            ) from None
        if requested_sender is not ConversationSender.AGENT:
            raise AppError(
                code="conversation.sender_not_allowed",
                message="Only agent messages can be created through this endpoint",
                status_code=403,
            )
        sent_at = utcnow()
        message = ConversationMessage(
            conversation_id=conversation_id,
            organization_id=organization_id,
            sender_type=requested_sender,
            sender_user_id=actor.id,
            body=data["body"],
            external_id=data.get("external_id"),
            metadata=data.get("metadata", {}),
            sent_at=sent_at,
        )
        self._messages.add(message)
        conversation.last_message_at = sent_at
        await commit_with_retry(self._session)
        return message

    async def record_inbound_lead_message(
        self,
        organization_id: uuid.UUID,
        conversation_id: uuid.UUID,
        data: dict[str, Any],
    ) -> ConversationMessage:
        """Record an inbound message from the lead on a trusted ingress path.

        This is the *only* way a ``LEAD`` sender is persisted by this service.
        It is deliberately not reachable from ordinary HTTP endpoints: callers
        must be trusted integrations (e.g. an email/WhatsApp ingress worker or
        an authenticated provider webhook) that vouch for the sender's
        identity. Ordinary authenticated clients go through ``add_message``,
        which accepts ``AGENT`` only.

        The provenance rules mirror the AGENT path: the sender is forced to
        ``LEAD``, ``sender_user_id`` is always NULL (the lead is not a
        user), and the timestamp is server-authoritative with provider
        timestamps accepted only when explicitly timezone-aware. The LEAD
        message and the thread's reopen happen in one transaction, so a
        failed message never reopens the conversation.
        """
        try:
            requested = ConversationSender(data.get("sender_type", ConversationSender.LEAD))
        except ValueError:
            raise AppError(
                code="conversation.invalid_sender",
                message="Unknown sender type",
                status_code=422,
            ) from None
        if requested is not ConversationSender.LEAD:
            raise AppError(
                code="conversation.sender_not_allowed",
                message="This path only records LEAD messages",
                status_code=403,
            )
        conversation = await self._conversations.get_or_404(
            organization_id, conversation_id
        )
        external_id = data.get("external_id")
        if external_id is not None:
            existing = await self._messages.get_by_external_id(
                organization_id, conversation_id, external_id
            )
            if existing is not None:
                # Duplicate provider delivery: idempotent no-op. The thread is
                # NOT re-timestamped and the conversation state is unchanged.
                return existing
        sent_at = _resolve_sent_at(data.get("sent_at"))
        message = ConversationMessage(
            conversation_id=conversation_id,
            organization_id=organization_id,
            sender_type=ConversationSender.LEAD,
            sender_user_id=None,
            body=data["body"],
            external_id=external_id,
            metadata=data.get("metadata", {}),
            sent_at=sent_at,
        )
        self._messages.add(message)
        conversation.last_message_at = sent_at
        if not conversation.is_open:
            # Trusted inbound LEAD replies reopen the thread (founder-approved
            # contract) inside the same transaction as the message insert.
            conversation.is_open = True
        await commit_with_retry(self._session)
        return message
