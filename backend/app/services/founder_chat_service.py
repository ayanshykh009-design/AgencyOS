"""Founder chat service — owns the conversation + message transaction boundary.

A turn is: persist the founder's message, run the :class:`FounderAssistantExecutor`,
persist the assistant's reply (and link any proposals the run produced), and
update conversation bookkeeping. The service never calls the LLM directly — that
is the executor's job — it only orchestrates persistence.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.executors.base import ExecutorContext
from app.agents.executors.registry import get_executor
from app.core.errors import AppError
from app.models.enums import FounderMessageSender
from app.models.founder_conversation import FounderConversation
from app.models.founder_message import FounderMessage
from app.models.user import User
from app.repositories.founder_conversation import FounderConversationRepository
from app.repositories.founder_message import FounderMessageRepository
from app.services.base import commit_with_retry, utcnow

logger = logging.getLogger("agencyos.founder.chat")

_MAX_TITLE = 60


class FounderChatService:
    """Orchestrates founder chat turns (org-scoped)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._conversations = FounderConversationRepository(session)
        self._messages = FounderMessageRepository(session)

    async def send_message(
        self,
        organization_id: uuid.UUID,
        user: User,
        *,
        conversation_id: uuid.UUID | None,
        message: str,
    ) -> dict:
        """Persist a founder turn and return the assistant's reply + proposals."""
        text = (message or "").strip()
        if not text:
            raise AppError(
                code="founder_chat.empty_message",
                message="A non-empty message is required",
                status_code=400,
            )

        conversation = await self._resolve_conversation(organization_id, conversation_id)
        user_msg = FounderMessage(
            conversation_id=conversation.id,
            organization_id=organization_id,
            sender_type=FounderMessageSender.USER,
            sender_user_id=user.id,
            body=text,
        )
        self._messages.add(user_msg)
        await self._session.flush()

        executor = get_executor("founder_assistant")
        if executor is None:
            raise AppError(
                code="founder_chat.no_executor",
                message="Founder assistant executor is not registered",
                status_code=503,
            )

        ctx = ExecutorContext(
            session=self._session,
            organization_id=organization_id,
            run_id=uuid.uuid4(),
            goal="founder_assistant",
            input={
                "message": text,
                "conversation_id": str(conversation.id),
                "actor_user_id": str(user.id),
            },
        )
        result = await executor.execute(ctx)

        now = utcnow()
        if result.success:
            response_text = (result.output or {}).get("response") or ""
            tool_calls = (result.output or {}).get("tool_calls") or []
            proposals = (result.output or {}).get("proposals") or []
            intent = (result.output or {}).get("intent") or {}
        else:
            response_text = (
                "I wasn't able to process that request. "
                + (result.error or "Please try again.")
            )
            tool_calls = []
            proposals = []
            intent = {}

        assistant_msg = FounderMessage(
            conversation_id=conversation.id,
            organization_id=organization_id,
            sender_type=FounderMessageSender.ASSISTANT,
            sender_user_id=user.id,
            body=response_text,
            metadata_={
                "ok": result.success,
                "tool_calls": tool_calls,
                "proposals": proposals,
                "intent": intent,
                "error": result.error,
            },
        )
        self._messages.add(assistant_msg)

        if conversation.title is None:
            conversation.title = text[:_MAX_TITLE] + ("…" if len(text) > _MAX_TITLE else "")
        conversation.last_message_at = now
        await commit_with_retry(self._session)

        return {
            "conversation_id": str(conversation.id),
            "message": {
                "id": str(assistant_msg.id),
                "sender": assistant_msg.sender_type.value,
                "body": assistant_msg.body,
                "sent_at": assistant_msg.sent_at.isoformat() if assistant_msg.sent_at else None,
            },
            "proposals": proposals,
            "intent": intent,
            "ok": result.success,
            "error": result.error,
        }

    async def list_conversations(
        self,
        organization_id: uuid.UUID,
        *,
        limit: int = 50,
        offset: int = 0,
        include_archived: bool = False,
    ) -> list[FounderConversation]:
        return await self._conversations.list_for_org(
            organization_id,
            limit=limit,
            offset=offset,
            include_archived=include_archived,
        )

    async def get_conversation(
        self, organization_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> dict:
        """Return a conversation with its (chronological) messages."""
        conversation = await self._conversations.get(organization_id, conversation_id)
        if conversation is None:
            raise AppError(
                code="founder_conversation.not_found",
                message="Conversation not found",
                status_code=404,
            )
        messages = await self._messages.list_by_conversation(
            organization_id, conversation_id
        )
        return {
            "conversation_id": str(conversation.id),
            "title": conversation.title,
            "is_archived": conversation.is_archived,
            "created_at": conversation.created_at.isoformat() if conversation.created_at else None,
            "last_message_at": (
                conversation.last_message_at.isoformat()
                if conversation.last_message_at
                else None
            ),
            "messages": [
                {
                    "id": str(m.id),
                    "sender": m.sender_type.value,
                    "body": m.body,
                    "sent_at": m.sent_at.isoformat() if m.sent_at else None,
                    "metadata": m.metadata_,
                }
                for m in messages
            ],
        }

    async def delete_conversation(
        self, organization_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> bool:
        return await self._conversations.delete(organization_id, conversation_id)

    async def _resolve_conversation(
        self, organization_id: uuid.UUID, conversation_id: uuid.UUID | None
    ) -> FounderConversation:
        if conversation_id is None:
            conversation = FounderConversation(organization_id=organization_id)
            self._conversations.add(conversation)
            await self._session.flush()
            return conversation
        found = await self._conversations.get(organization_id, conversation_id)
        if found is None:
            raise AppError(
                code="founder_conversation.not_found",
                message="Conversation not found",
                status_code=404,
            )
        return found
