"""Pipeline API schemas: stages, close reasons, and the Kanban board."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import StageLifecycle
from app.schemas.lead import LeadRead


class PipelineStageCreate(BaseModel):
    """Payload to create a pipeline stage."""

    name: str = Field(min_length=1, max_length=255)
    lifecycle: StageLifecycle = StageLifecycle.OPEN
    position: int | None = Field(default=None, ge=0)


class PipelineStageUpdate(BaseModel):
    """Partial update of a pipeline stage (lifecycle is immutable)."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    position: int | None = Field(default=None, ge=0)


class PipelineStageRead(BaseModel):
    """Full pipeline stage representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    name: str
    lifecycle: StageLifecycle
    position: int
    is_default: bool
    lead_count: int = 0
    created_at: datetime
    updated_at: datetime


class StageReorderRequest(BaseModel):
    """Ordered list of stage ids; every stage must appear exactly once."""

    stage_ids: list[UUID]


class CloseReasonCreate(BaseModel):
    """Payload to create a close reason (won or lost)."""

    name: str = Field(min_length=1, max_length=255)
    lifecycle: StageLifecycle


class CloseReasonRead(BaseModel):
    """Full close reason representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    lifecycle: StageLifecycle
    name: str
    is_default: bool
    created_at: datetime


class LeadStageMoveRequest(BaseModel):
    """Move a lead onto a pipeline stage (optionally closing it)."""

    stage_id: UUID
    close_reason_id: UUID | None = None


class PipelineStageWithLeads(BaseModel):
    """A Kanban board column: the stage plus its (capped) lead cards."""

    stage: PipelineStageRead
    leads: list[LeadRead]
