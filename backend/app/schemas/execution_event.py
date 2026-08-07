"""ExecutionEvent schemas (append-only execution timeline)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.enums import ExecutionEventType
from app.schemas.common import Page


class ExecutionEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    execution_id: uuid.UUID
    attempt: int
    event_type: ExecutionEventType
    metadata: dict[str, Any]
    occurred_at: datetime
    created_at: datetime


class ExecutionEventListResponse(Page[ExecutionEventRead]):
    pass
