"""SystemSetting schemas (operator key/value settings)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SystemSettingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key: str
    value: dict[str, Any]
    updated_by_user_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class SystemSettingUpsert(BaseModel):
    value: dict[str, Any] = Field(default_factory=dict)


# Automation control schemas
class SystemSettingStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    enabled: bool
    paused_by: str | None = None
    paused_at: datetime | None = None
    paused_reason: str | None = None


class SystemSettingPauseRequest(BaseModel):
    reason: str


class SystemSettingResumeRequest(BaseModel):
    pass
