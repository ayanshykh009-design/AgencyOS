"""Note API schemas: create/update/read models for lead notes."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class NoteCreate(BaseModel):
    """Payload to create a note on a lead."""

    lead_id: UUID
    body: str = Field(min_length=1, max_length=20_000)
    pinned: bool = False


class NoteUpdate(BaseModel):
    """Partial update of a note (all fields optional)."""

    body: str | None = Field(default=None, min_length=1, max_length=20_000)
    pinned: bool | None = None


class NoteRead(BaseModel):
    """Full note representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    lead_id: UUID
    author_user_id: UUID | None
    body: str
    pinned: bool
    created_at: datetime
    updated_at: datetime
