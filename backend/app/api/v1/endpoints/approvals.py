"""Approval endpoints: gated approval requests + immutable audit log."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, DbSession
from app.core.permissions import Permission, require_permission
from app.models.enums import ApprovalRequestStatus
from app.schemas.approval import (
    ApprovalLogListResponse,
    ApprovalLogRead,
    ApprovalPendingCount,
    ApprovalRequestCreate,
    ApprovalRequestDecision,
    ApprovalRequestListResponse,
    ApprovalRequestRead,
)
from app.services.approval_service import ApprovalService

router = APIRouter()

_read = Depends(require_permission(Permission.APPROVAL_READ))
_manage = Depends(require_permission(Permission.APPROVAL_MANAGE))


@router.get(
    "",
    response_model=ApprovalRequestListResponse,
    summary="List approval requests (optional status filter)",
    dependencies=[_read],
)
async def list_approvals(
    db: DbSession,
    current_user: CurrentUser,
    status: ApprovalRequestStatus | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> ApprovalRequestListResponse:
    service = ApprovalService(db)
    items = await service.list_requests(
        current_user.organization_id, status=status, limit=limit, offset=offset
    )
    return ApprovalRequestListResponse(
        items=[ApprovalRequestRead.model_validate(r) for r in items], total=len(items)
    )


@router.post(
    "",
    response_model=ApprovalRequestRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an approval request",
    dependencies=[_manage],
)
async def create_approval(
    body: ApprovalRequestCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> ApprovalRequestRead:
    service = ApprovalService(db)
    data = body.model_dump(exclude={"organization_id"})
    request = await service.create_request(
        current_user.organization_id,
        requested_by_user_id=current_user.id,
        actor=current_user,
        **data,
    )
    return ApprovalRequestRead.model_validate(request)


@router.get(
    "/pending-count",
    response_model=ApprovalPendingCount,
    summary="Open (pending) approval request count",
    dependencies=[_read],
)
async def pending_count(db: DbSession, current_user: CurrentUser) -> ApprovalPendingCount:
    service = ApprovalService(db)
    count = await service.pending_count(current_user.organization_id)
    return ApprovalPendingCount(count=count)


@router.post(
    "/{request_id}/decision",
    response_model=ApprovalRequestRead,
    summary="Approve or deny a pending approval request",
    dependencies=[_manage],
)
async def decide_approval(
    request_id: uuid.UUID,
    body: ApprovalRequestDecision,
    db: DbSession,
    current_user: CurrentUser,
) -> ApprovalRequestRead:
    service = ApprovalService(db)
    data = body.model_dump(exclude_unset=True)
    request = await service.decide(
        current_user.organization_id,
        current_user,
        request_id,
        approve=data.pop("approve"),
        decided_by_user_id=data.pop("decided_by_user_id", None),
        decision_note=data.pop("decision_note", None),
    )
    return ApprovalRequestRead.model_validate(request)


@router.get(
    "/{request_id}",
    response_model=ApprovalRequestRead,
    summary="Get an approval request",
    dependencies=[_read],
)
async def get_approval(
    request_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> ApprovalRequestRead:
    service = ApprovalService(db)
    request = await service.get_request(current_user.organization_id, request_id)
    return ApprovalRequestRead.model_validate(request)


@router.get(
    "/{request_id}/logs",
    response_model=ApprovalLogListResponse,
    summary="Audit timeline for an approval request (oldest first)",
    dependencies=[_read],
)
async def list_approval_logs(
    request_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ApprovalLogListResponse:
    service = ApprovalService(db)
    logs = await service.list_logs(
        current_user.organization_id, request_id, limit=limit, offset=offset
    )
    return ApprovalLogListResponse(
        items=[ApprovalLogRead.model_validate(entry) for entry in logs],
        total=len(logs),
    )
