"""Lead assignment API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AssignmentMethod, AssignmentStrategy


class AssignmentRuleWrite(BaseModel):
    """Payload to create or update the org's assignment rule."""

    name: str = Field(min_length=1, max_length=255)
    strategy: AssignmentStrategy = AssignmentStrategy.MANUAL
    enabled: bool = False
    target_user_ids: list[UUID] = Field(default_factory=list)
    conditions: dict[str, Any] = Field(default_factory=dict)


class AssignmentRuleRead(BaseModel):
    """The org's assignment rule."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    name: str
    strategy: AssignmentStrategy
    enabled: bool
    target_user_ids: list[UUID]
    conditions: dict[str, Any]
    last_assigned_index: int
    created_at: datetime
    updated_at: datetime


class LeadAssignRequest(BaseModel):
    """Manual assignment payload."""

    user_id: UUID | None = None
    reason: str | None = Field(default=None, max_length=255)


class AssignmentLogRead(BaseModel):
    """A single ownership-change record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    lead_id: UUID
    from_user_id: UUID | None = None
    to_user_id: UUID | None = None
    method: AssignmentMethod
    assigned_by_user_id: UUID | None = None
    reason: str | None = None
    created_at: datetime
