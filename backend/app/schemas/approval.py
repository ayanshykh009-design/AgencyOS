"""Approval schemas (gated requests + immutable audit log)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ApprovalLogAction, ApprovalRequestStatus
from app.schemas.common import Page


class ApprovalRequestCreate(BaseModel):
    workflow_id: uuid.UUID | None = None
    workflow_execution_id: uuid.UUID | None = None
    requested_by_user_id: uuid.UUID | None = None
    approver_user_id: uuid.UUID | None = None
    title: str = Field(min_length=1, max_length=500)
    details: str | None = None
    expires_at: datetime | None = None


class ApprovalRequestDecision(BaseModel):
    """Payload to approve/deny a pending request."""

    approve: bool
    decided_by_user_id: uuid.UUID | None = None
    decision_note: str | None = Field(default=None, max_length=2000)


class ApprovalRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    workflow_id: uuid.UUID | None = None
    workflow_execution_id: uuid.UUID | None = None
    requested_by_user_id: uuid.UUID | None = None
    approver_user_id: uuid.UUID | None = None
    title: str
    details: str | None = None
    status: ApprovalRequestStatus
    expires_at: datetime
    decided_by_user_id: uuid.UUID | None = None
    decided_at: datetime | None = None
    decision_note: str | None = None
    created_at: datetime
    updated_at: datetime


class ApprovalPendingCount(BaseModel):
    """Open (pending) approval request count for an organization."""

    count: int


class ApprovalRequestListResponse(Page[ApprovalRequestRead]):
    pass


class ApprovalLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    approval_request_id: uuid.UUID
    actor_user_id: uuid.UUID | None = None
    action: ApprovalLogAction
    note: str | None = None
    occurred_at: datetime
    created_at: datetime


class ApprovalLogListResponse(Page[ApprovalLogRead]):
    pass
