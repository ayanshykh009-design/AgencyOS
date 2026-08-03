"""Task API schemas: create/update/read models for the tasks feature."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import RecurrenceFrequency, TaskPriority, TaskStatus


class TaskCreate(BaseModel):
    """Payload to create a task."""

    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10_000)
    lead_id: UUID | None = None
    assignee_user_id: UUID | None = None
    due_at: datetime | None = None
    reminder_at: datetime | None = None
    priority: TaskPriority = TaskPriority.MEDIUM
    recurrence_frequency: RecurrenceFrequency | None = None
    recurrence_interval: int | None = Field(default=None, ge=1)


class TaskUpdate(BaseModel):
    """Partial update of a task (all fields optional)."""

    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10_000)
    lead_id: UUID | None = None
    assignee_user_id: UUID | None = None
    due_at: datetime | None = None
    reminder_at: datetime | None = None
    priority: TaskPriority | None = None
    status: TaskStatus | None = None
    recurrence_frequency: RecurrenceFrequency | None = None
    recurrence_interval: int | None = Field(default=None, ge=1)


class TaskRead(BaseModel):
    """Full task representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    lead_id: UUID | None
    assignee_user_id: UUID | None
    created_by_user_id: UUID | None
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    due_at: datetime | None
    reminder_at: datetime | None
    completed_at: datetime | None
    recurrence_frequency: RecurrenceFrequency | None
    recurrence_interval: int | None
    created_at: datetime
    updated_at: datetime
