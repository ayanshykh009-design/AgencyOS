"""Agent run schemas (per-run execution records).

Status is runtime-owned: ``AgentRunUpdate`` intentionally exposes no ``status``
field, so clients can never force a run through the state machine. The runtime
moves runs via guarded transitions in the service/repository, never via PATCH.
"""
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
    # Idempotency key: re-creating with the same (org, key) returns the existing
    # run instead of queuing a duplicate.
    idempotency_key: str | None = Field(default=None, max_length=200)


class AgentRunUpdate(BaseModel):
    # NOTE: status is intentionally absent — the runtime owns all transitions.
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
    cancel_requested_at: datetime | None = None
    cancelled_by_user_id: uuid.UUID | None = None
    idempotency_key: str | None = None
    created_at: datetime
    updated_at: datetime


class AgentRunListResponse(Page[AgentRunRead]):
    pass
