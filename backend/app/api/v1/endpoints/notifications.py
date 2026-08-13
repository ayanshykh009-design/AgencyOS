"""Notification endpoints: per-user in-app inbox."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, DbSession
from app.core.permissions import Permission, require_permission
from app.schemas.notification import (
    NotificationCreate,
    NotificationListResponse,
    NotificationRead,
    NotificationTypeCounts,
    NotificationUnreadCount,
    NotificationUpdate,
)
from app.services.notification_service import NotificationService

router = APIRouter()

_read = Depends(require_permission(Permission.NOTIFICATION_READ))
_write = Depends(require_permission(Permission.NOTIFICATION_WRITE))


@router.get(
    "",
    response_model=NotificationListResponse,
    summary="List the current user's notifications",
    dependencies=[_read],
)
async def list_notifications(
    db: DbSession,
    current_user: CurrentUser,
    only_unread: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> NotificationListResponse:
    service = NotificationService(db)
    items = await service.list_for_user(
        current_user.organization_id,
        current_user.id,
        only_unread=only_unread,
        limit=limit,
        offset=offset,
    )
    return NotificationListResponse(
        items=[NotificationRead.model_validate(n) for n in items], total=len(items)
    )


@router.get(
    "/unread-count",
    response_model=NotificationUnreadCount,
    summary="Unread badge count for the current user",
    dependencies=[_read],
)
async def unread_count(db: DbSession, current_user: CurrentUser) -> NotificationUnreadCount:
    service = NotificationService(db)
    count = await service.unread_count(current_user.organization_id, current_user.id)
    return NotificationUnreadCount(count=count)


@router.get(
    "/counts",
    response_model=NotificationTypeCounts,
    summary="Notification counts grouped by type",
    dependencies=[_read],
)
async def counts_by_type(db: DbSession, current_user: CurrentUser) -> NotificationTypeCounts:
    service = NotificationService(db)
    counts = await service.counts_by_type(current_user.organization_id)
    return NotificationTypeCounts(counts=counts)


@router.post(
    "",
    response_model=NotificationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a notification (system/worker)",
    dependencies=[_write],
)
async def create_notification(
    body: NotificationCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> NotificationRead:
    service = NotificationService(db)
    data = body.model_dump(exclude={"organization_id"})
    metadata = data.pop("metadata", None) or {}
    notification = await service.create(current_user.organization_id, metadata_=metadata, **data)
    return NotificationRead.model_validate(notification)


@router.get(
    "/{notification_id}",
    response_model=NotificationRead,
    summary="Get a notification owned by the current user",
    dependencies=[_read],
)
async def get_notification(
    notification_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> NotificationRead:
    service = NotificationService(db)
    notification = await service.get_for_user(
        current_user.organization_id, current_user.id, notification_id
    )
    return NotificationRead.model_validate(notification)


@router.patch(
    "/{notification_id}",
    response_model=NotificationRead,
    summary="Update a notification (e.g. mark read/unread)",
    dependencies=[_read],
)
async def update_notification(
    notification_id: uuid.UUID,
    body: NotificationUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> NotificationRead:
    service = NotificationService(db)
    data = body.model_dump(exclude_unset=True)
    if "is_read" not in data:
        from app.core.errors import AppError

        raise AppError(
            code="notification.is_read_required",
            message="is_read is required",
            status_code=400,
        )
    notification = await service.set_read(
        current_user.organization_id,
        current_user.id,
        notification_id,
        is_read=data["is_read"],
    )
    return NotificationRead.model_validate(notification)


@router.post(
    "/{notification_id}/read",
    response_model=NotificationRead,
    summary="Mark a notification read",
    dependencies=[_read],
)
async def mark_notification_read(
    notification_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> NotificationRead:
    service = NotificationService(db)
    notification = await service.set_read(
        current_user.organization_id,
        current_user.id,
        notification_id,
        is_read=True,
    )
    return NotificationRead.model_validate(notification)
