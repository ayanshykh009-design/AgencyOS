"""Outreach API schemas: message templates, attempts, follow-ups, manual queue."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import OutreachChannel, OutreachStatus

# ---------------------------------------------------------------------------
# outreach_messages
# ---------------------------------------------------------------------------


class OutreachMessageBase(BaseModel):
    """Fields a client can set on a message template."""

    name: str = Field(min_length=1, max_length=255)
    channel: OutreachChannel
    subject: str | None = None
    body: str = Field(min_length=1)
    variables: list[str] = Field(default_factory=list)
    version: int = Field(default=1, ge=1)
    is_active: bool = True


class OutreachMessageCreate(OutreachMessageBase):
    """Payload to create a message template."""

    organization_id: UUID


class OutreachMessageUpdate(BaseModel):
    """Partial update of a message template (all fields optional)."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    channel: OutreachChannel | None = None
    subject: str | None = None
    body: str | None = Field(default=None, min_length=1)
    variables: list[str] | None = None
    version: int | None = Field(default=None, ge=1)
    is_active: bool | None = None


class OutreachMessageRead(OutreachMessageBase):
    """Full message template returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# outreach_attempts
# ---------------------------------------------------------------------------


class OutreachAttemptBase(BaseModel):
    """Fields a client can set on an outreach attempt."""

    model_config = ConfigDict(populate_by_name=True)

    channel: OutreachChannel
    status: OutreachStatus = OutreachStatus.QUEUED
    subject: str | None = None
    body: str | None = None
    scheduled_at: datetime | None = None
    metadata: dict[str, Any] = Field(
        default_factory=dict, alias="metadata_", serialization_alias="metadata"
    )


class OutreachAttemptCreate(OutreachAttemptBase):
    """Payload to create an outreach attempt."""

    organization_id: UUID
    lead_id: UUID
    outreach_message_id: UUID | None = None


class OutreachAttemptUpdate(BaseModel):
    """Partial update of an outreach attempt (all fields optional)."""

    model_config = ConfigDict(populate_by_name=True)

    status: OutreachStatus | None = None
    scheduled_at: datetime | None = None
    sent_at: datetime | None = None
    delivered_at: datetime | None = None
    external_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] | None = Field(
        default=None, alias="metadata_", serialization_alias="metadata"
    )


class OutreachAttemptRead(OutreachAttemptBase):
    """Full outreach attempt returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    lead_id: UUID
    outreach_message_id: UUID | None = None
    sent_at: datetime | None = None
    delivered_at: datetime | None = None
    external_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# follow_ups
# ---------------------------------------------------------------------------


class FollowUpBase(BaseModel):
    """Fields a client can set on a follow-up."""

    channel: OutreachChannel
    sequence_position: int = Field(ge=1)
    subject: str | None = None
    body: str = Field(min_length=1)
    delay_days: int = Field(default=0, ge=0)
    scheduled_at: datetime | None = None
    status: OutreachStatus = OutreachStatus.QUEUED


class FollowUpCreate(FollowUpBase):
    """Payload to create a follow-up."""

    organization_id: UUID
    lead_id: UUID
    outreach_attempt_id: UUID | None = None


class FollowUpUpdate(BaseModel):
    """Partial update of a follow-up (all fields optional)."""

    subject: str | None = None
    body: str | None = Field(default=None, min_length=1)
    delay_days: int | None = Field(default=None, ge=0)
    scheduled_at: datetime | None = None
    status: OutreachStatus | None = None
    sent_at: datetime | None = None


class FollowUpRead(FollowUpBase):
    """Full follow-up returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    lead_id: UUID
    outreach_attempt_id: UUID | None = None
    sent_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# manual_outreach_queue
# ---------------------------------------------------------------------------


class ManualOutreachQueueBase(BaseModel):
    """Fields a client can set on a manual outreach task."""

    channel: OutreachChannel
    status: OutreachStatus = OutreachStatus.QUEUED
    priority: int = Field(default=0, ge=0)
    due_at: datetime | None = None
    subject: str | None = None
    body: str | None = None
    notes: str | None = None


class ManualOutreachQueueCreate(ManualOutreachQueueBase):
    """Payload to create a manual outreach task."""

    organization_id: UUID
    lead_id: UUID
    assigned_user_id: UUID | None = None


class ManualOutreachQueueUpdate(BaseModel):
    """Partial update of a manual outreach task (all fields optional)."""

    status: OutreachStatus | None = None
    priority: int | None = Field(default=None, ge=0)
    due_at: datetime | None = None
    subject: str | None = None
    body: str | None = None
    notes: str | None = None
    assigned_user_id: UUID | None = None
    completed_at: datetime | None = None


class ManualOutreachQueueRead(ManualOutreachQueueBase):
    """Full manual outreach task returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    lead_id: UUID
    assigned_user_id: UUID | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
