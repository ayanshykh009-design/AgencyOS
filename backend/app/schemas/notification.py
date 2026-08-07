"""Notification schemas (in-app inbox)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import NotificationType
from app.schemas.common import Page


class NotificationBase(BaseModel):
    user_id: uuid.UUID | None = None
    type: NotificationType
    title: str = Field(min_length=1, max_length=500)
    body: str = Field(min_length=1)
    action_url: str | None = None
    metadata: dict[str, Any] = Field(
        default_factory=dict, alias="metadata_", serialization_alias="metadata"
    )


class NotificationCreate(NotificationBase):
    organization_id: uuid.UUID


class NotificationUpdate(BaseModel):
    is_read: bool | None = None


class NotificationRead(NotificationBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    is_read: bool
    read_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class NotificationListResponse(Page[NotificationRead]):
    pass
