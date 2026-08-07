"""Agent run schemas (per-run execution records)."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AgentRunStatus, AgentRunTrigger
from app.schemas.common import Page


class AgentRunBase(BaseModel):
    agent_name: str = Field(min_length=1, max_length=200)
    status: AgentRunStatus = AgentRunStatus.QUEUED
    trigger: AgentRunTrigger = AgentRunTrigger.MANUAL
    workflow_id: uuid.UUID | None = None
    input: dict[str, Any] = Field(default_factory=dict)


class AgentRunCreate(AgentRunBase):
    organization_id: uuid.UUID


class AgentRunUpdate(BaseModel):
    status: AgentRunStatus | None = None
    output: dict[str, Any] | None = None
    error: str | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    cost: Decimal | None = Field(default=None, ge=0)
    started_at: datetime | None = None
    finished_at: datetime | None = None


class AgentRunRead(AgentRunBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    output: dict[str, Any] | None = None
    error: str | None = None
    duration_ms: int | None = None
    cost: Decimal
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class AgentRunListResponse(Page[AgentRunRead]):
    pass
