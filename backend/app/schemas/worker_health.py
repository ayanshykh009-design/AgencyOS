"""WorkerHealth schemas (automation worker heartbeats)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class WorkerHealthRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    worker_type: str
    instance_id: uuid.UUID
    pid: int
    hostname: str
    loop_ok: bool
    last_error: str | None = None
    counters: dict[str, Any]
    last_heartbeat_at: datetime
    updated_at: datetime
