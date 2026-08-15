"""Founder Assistant schemas (M8 chat + proposals)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import FounderActionType, FounderProposalStatus


class FounderChatRequest(BaseModel):
    """A founder turn: a message plus an optional existing conversation."""

    message: str = Field(min_length=1, max_length=8000)
    conversation_id: uuid.UUID | None = None


class FounderMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    sender: str
    body: str
    sent_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, alias="metadata_")


class FounderProposalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    conversation_id: uuid.UUID | None = None
    action_type: FounderActionType
    title: str
    status: FounderProposalStatus
    justification: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    expires_at: datetime | None = None
    decided_at: datetime | None = None
    created_at: datetime | None = None


class FounderChatResponse(BaseModel):
    conversation_id: uuid.UUID
    message: FounderMessageRead
    proposals: list[FounderProposalRead] = Field(default_factory=list)
    intent: dict[str, Any] = Field(default_factory=dict)
    ok: bool = True
    error: str | None = None


class FounderConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    conversation_id: uuid.UUID = Field(alias="id")
    title: str | None = None
    is_archived: bool = False
    created_at: datetime | None = None
    last_message_at: datetime | None = None


class FounderConversationList(BaseModel):
    items: list[FounderConversationRead] = Field(default_factory=list)
    total: int = 0


class FounderProposalDecision(BaseModel):
    approve: bool
    decision_note: str | None = None


class FounderProposalList(BaseModel):
    items: list[FounderProposalRead] = Field(default_factory=list)
    total: int = 0
