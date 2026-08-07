"""Agent state schemas (per-agent health bookkeeping)."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AgentHealth, AgentStateStatus
from app.schemas.common import Page


class AgentStateUpsert(BaseModel):
    agent_name: str = Field(min_length=1, max_length=200)
    status: AgentStateStatus = AgentStateStatus.ACTIVE
    health: AgentHealth = AgentHealth.HEALTHY
    queue_depth: int = Field(default=0, ge=0)
    total_runs: int = Field(default=0, ge=0)
    average_runtime_ms: Decimal = Field(default=Decimal("0"), ge=0)
    average_cost: Decimal = Field(default=Decimal("0"), ge=0)
    last_execution: datetime | None = None
    last_error: str | None = None


class AgentStateRead(AgentStateUpsert):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class AgentStateListResponse(Page[AgentStateRead]):
    pass
