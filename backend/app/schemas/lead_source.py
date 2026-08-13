"""LeadSource API schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import OutreachChannel


class LeadSourceBase(BaseModel):
    """Fields a client can set on a lead source."""

    name: str = Field(min_length=1, max_length=255)
    channel: OutreachChannel = OutreachChannel.CONTACT_FORM
    description: str | None = None
    is_active: bool = True


class LeadSourceCreate(LeadSourceBase):
    """Payload to create a lead source."""


class LeadSourceUpdate(BaseModel):
    """Partial update of a lead source (all fields optional)."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    channel: OutreachChannel | None = None
    description: str | None = None
    is_active: bool | None = None


class LeadSourceRead(LeadSourceBase):
    """Full lead source representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    created_at: datetime
    updated_at: datetime
