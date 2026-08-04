"""WorkflowTrigger schemas."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import WorkflowTriggerType
from app.schemas.common import Page


class WorkflowTriggerBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    trigger_type: WorkflowTriggerType
    event_type: str | None = Field(default=None, min_length=1)
    schedule_cron: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class WorkflowTriggerCreate(WorkflowTriggerBase):
    organization_id: uuid.UUID | None = None
    workflow_id: uuid.UUID


class WorkflowTriggerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    trigger_type: WorkflowTriggerType | None = None
    event_type: str | None = Field(default=None, min_length=1)
    schedule_cron: str | None = None
    config: dict[str, Any] | None = None
    enabled: bool | None = None


class WorkflowTriggerRead(WorkflowTriggerBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    workflow_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class WorkflowTriggerListResponse(Page[WorkflowTriggerRead]):
    pass
