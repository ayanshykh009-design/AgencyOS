"""Workflow schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import WorkflowStatus
from app.schemas.common import Page


class WorkflowBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    definition: dict[str, Any] = Field(default_factory=dict)
    execution_mode: str = Field(default="n8n", pattern="^(n8n|builtin)$")
    config: dict[str, Any] = Field(default_factory=dict)


class WorkflowCreate(WorkflowBase):
    organization_id: uuid.UUID | None = None


class WorkflowUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    definition: dict[str, Any] | None = None
    status: WorkflowStatus | None = None
    execution_mode: str | None = Field(default=None, pattern="^(n8n|builtin)$")
    config: dict[str, Any] | None = None


class WorkflowRead(WorkflowBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    status: WorkflowStatus
    version: int
    created_by_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class WorkflowListResponse(Page[WorkflowRead]):
    pass
