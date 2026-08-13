"""WorkflowExecution schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ExecutionStatus
from app.schemas.common import Page


class WorkflowExecutionBase(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)
    max_attempts: int = Field(default=3, ge=1, le=10)
    retry_delay_seconds: int = Field(default=60, ge=0)
    retry_backoff: str = Field(default="exponential", pattern="^(constant|exponential)$")


class WorkflowExecutionCreate(WorkflowExecutionBase):
    organization_id: uuid.UUID | None = None
    workflow_id: uuid.UUID
    trigger_id: uuid.UUID | None = None
    trace_id: uuid.UUID | None = None
    idempotency_key: str | None = Field(default=None, max_length=255)


class WorkflowExecutionRead(WorkflowExecutionBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    workflow_id: uuid.UUID
    trigger_id: uuid.UUID | None
    status: ExecutionStatus
    output: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    attempts: int
    next_retry_at: datetime | None = None
    requested_by_user_id: uuid.UUID | None = None
    trace_id: uuid.UUID | None = None
    idempotency_key: str | None = None
    cancel_requested_at: datetime | None = None
    cancelled_by_user_id: uuid.UUID | None = None
    duration_ms: int | None = None
    created_at: datetime
    updated_at: datetime


class WorkflowExecutionQueue(BaseModel):
    """Response envelope for the queue endpoint (execution_id + initial status)."""

    execution_id: uuid.UUID
    status: ExecutionStatus


class WorkflowExecutionListResponse(Page[WorkflowExecutionRead]):
    pass
