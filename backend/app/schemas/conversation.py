"""Conversation API schemas: threads and thread messages."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ConversationSender, OutreachChannel


class ConversationBase(BaseModel):
    """Fields a client can set on a conversation."""

    channel: OutreachChannel
    external_thread_id: str | None = None
    subject: str | None = None
    is_open: bool = True


class ConversationCreate(ConversationBase):
    """Payload to create a conversation."""

    organization_id: UUID
    lead_id: UUID


class ConversationUpdate(BaseModel):
    """Partial update of a conversation (all fields optional)."""

    subject: str | None = None
    is_open: bool | None = None
    last_message_at: datetime | None = None


class ConversationRead(ConversationBase):
    """Full conversation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    lead_id: UUID
    last_message_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ConversationMessageBase(BaseModel):
    """Fields a client can set on a thread message."""

    model_config = ConfigDict(populate_by_name=True)

    sender_type: ConversationSender
    sender_user_id: UUID | None = None
    body: str = Field(min_length=1)
    external_id: str | None = None
    metadata: dict[str, Any] = Field(
        default_factory=dict, alias="metadata_", serialization_alias="metadata"
    )
    sent_at: datetime | None = None


class ConversationMessageCreate(ConversationMessageBase):
    """Payload to create a thread message."""

    conversation_id: UUID
    organization_id: UUID


class ConversationMessageRead(ConversationMessageBase):
    """Full thread message returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: UUID
    organization_id: UUID
    created_at: datetime
