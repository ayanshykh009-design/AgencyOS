"""ActivityLog API schemas (append-only audit trail)."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ActivityEventType


class ActivityLogCreate(BaseModel):
    """Payload to record a business event."""

    model_config = ConfigDict(populate_by_name=True)

    organization_id: UUID
    user_id: UUID | None = None
    lead_id: UUID | None = None
    event_type: ActivityEventType
    entity_type: str | None = None
    entity_id: UUID | None = None
    description: str | None = None
    metadata: dict[str, Any] = Field(
        default_factory=dict, alias="metadata_", serialization_alias="metadata"
    )
    occurred_at: datetime | None = None


class ActivityLogRead(BaseModel):
    """Full activity log entry returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    user_id: UUID | None = None
    lead_id: UUID | None = None
    event_type: ActivityEventType
    entity_type: str | None = None
    entity_id: UUID | None = None
    description: str | None = None
    metadata: dict[str, Any] = Field(
        default_factory=dict, alias="metadata_", serialization_alias="metadata"
    )
    occurred_at: datetime
    created_at: datetime

    # Actor metadata resolved for audit views (None when unavailable).
    actor_user_id: UUID | None = None
    actor_name: str | None = None
