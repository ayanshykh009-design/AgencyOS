"""WorkflowEvent schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Page


class WorkflowEventBase(BaseModel):
    event_type: str = Field(min_length=1, max_length=100)
    payload: dict[str, Any] = Field(default_factory=dict)


class WorkflowEventCreate(WorkflowEventBase):
    organization_id: uuid.UUID | None = None


class WorkflowEventRead(WorkflowEventBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    consumed: bool
    consumed_at: datetime | None = None
    occurred_at: datetime


class WorkflowEventPublish(BaseModel):
    """Response envelope for the publish endpoint."""

    event_id: uuid.UUID
    consumed: bool


class WorkflowEventListResponse(Page[WorkflowEventRead]):
    pass
