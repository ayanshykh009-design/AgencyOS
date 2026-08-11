"""Delivery schemas (M6 outbox + timeline)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import DeliveryChannel, DeliveryEventType, DeliveryStatus
from app.schemas.common import Page


class DeliveryCreate(BaseModel):
    """Payload to enqueue a new delivery."""

    channel: DeliveryChannel
    recipient_user_id: uuid.UUID | None = None
    notification_id: uuid.UUID | None = None
    approval_request_id: uuid.UUID | None = None
    subject: str = Field(min_length=1, max_length=500)
    body: str = Field(min_length=1)
    action_url: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    max_attempts: int | None = Field(default=None, ge=1, le=10)
    scheduled_for: datetime | None = None
    idempotency_key: str | None = Field(default=None, max_length=255)


class DeliveryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    channel: DeliveryChannel
    recipient_user_id: uuid.UUID | None = None
    notification_id: uuid.UUID | None = None
    approval_request_id: uuid.UUID | None = None
    subject: str
    body: str
    action_url: str | None = None
    status: DeliveryStatus
    attempts: int
    max_attempts: int
    next_attempt_at: datetime | None = None
    attempt_started_at: datetime | None = None
    cancel_requested_at: datetime | None = None
    cancelled_by_user_id: uuid.UUID | None = None
    last_error: str | None = None
    provider_metadata: dict[str, Any]
    payload: dict[str, Any]
    idempotency_key: str | None = None
    scheduled_for: datetime
    delivered_at: datetime | None = None
    failed_at: datetime | None = None
    cancelled_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class DeliveryListResponse(Page[DeliveryRead]):
    pass


class DeliveryRetry(BaseModel):
    """Manual retry of a failed/cancelled delivery."""

    pass


class DeliveryCancel(BaseModel):
    """Cancel a queued/processing delivery."""

    pass


class DeliveryEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    delivery_id: uuid.UUID
    event_type: DeliveryEventType
    attempt: int
    metadata: dict[str, Any] = Field(
        default_factory=dict, alias="metadata_", serialization_alias="metadata"
    )
    occurred_at: datetime
    created_at: datetime


class DeliveryEventListResponse(Page[DeliveryEventRead]):
    pass


class DeliveryStatistics(BaseModel):
    """Delivery monitoring statistics."""

    queued: int
    processing: int
    retrying: int
    delivered: int
    failed: int
    cancelled: int
    pending_cap_utilization_pct: float


class DeliveryWorkerHealth(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    worker_type: str
    instance_id: uuid.UUID
    pid: int
    hostname: str
    loop_ok: bool
    last_error: str | None = None
    counters: dict[str, int]
    last_heartbeat_at: datetime
    created_at: datetime


class DeliveryWorkerHealthListResponse(Page[DeliveryWorkerHealth]):
    pass