"""Delivery endpoints: outbox management + timeline + monitoring.

All endpoints are JWT-authenticated. Reads require ``delivery_read``; writes
require ``delivery_write``; admin actions require ``delivery_manage``.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, DbSession
from app.core.permissions import Permission, require_permission
from app.models.enums import DeliveryChannel, DeliveryStatus
from app.schemas.delivery import (
    DeliveryCancel,
    DeliveryCreate,
    DeliveryEventListResponse,
    DeliveryEventRead,
    DeliveryListResponse,
    DeliveryRead,
    DeliveryRetry,
)
from app.services.delivery_service import DeliveryService

router = APIRouter()

_read = Depends(require_permission(Permission.DELIVERY_READ))
_write = Depends(require_permission(Permission.DELIVERY_WRITE))
_manage = Depends(require_permission(Permission.DELIVERY_MANAGE))


@router.get(
    "",
    response_model=DeliveryListResponse,
    summary="List deliveries (optional status/channel/recipient filter)",
    dependencies=[_read],
)
async def list_deliveries(
    db: DbSession,
    current_user: CurrentUser,
    status: DeliveryStatus | None = None,
    channel: DeliveryChannel | None = None,
    recipient_user_id: uuid.UUID | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> DeliveryListResponse:
    service = DeliveryService(db)
    items = await service.list_deliveries(
        current_user.organization_id,
        status=status,
        channel=channel,
        recipient_user_id=recipient_user_id,
        limit=limit,
        offset=offset,
    )
    return DeliveryListResponse(
        items=[DeliveryRead.model_validate(r) for r in items], total=len(items)
    )


@router.post(
    "",
    response_model=DeliveryRead,
    status_code=status.HTTP_201_CREATED,
    summary="Enqueue a new delivery",
    dependencies=[_write],
)
async def create_delivery(
    body: DeliveryCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> DeliveryRead:
    service = DeliveryService(db)
    data = body.model_dump(exclude={"organization_id"})
    delivery = await service.enqueue(
        current_user.organization_id,
        **data,
    )
    return DeliveryRead.model_validate(delivery)


@router.get(
    "/{delivery_id}",
    response_model=DeliveryRead,
    summary="Get a delivery by ID",
    dependencies=[_read],
)
async def get_delivery(
    delivery_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> DeliveryRead:
    service = DeliveryService(db)
    delivery = await service.get(current_user.organization_id, delivery_id)
    return DeliveryRead.model_validate(delivery)


@router.get(
    "/{delivery_id}/events",
    response_model=DeliveryEventListResponse,
    summary="Get the append-only timeline for a delivery",
    dependencies=[_read],
)
async def get_delivery_events(
    delivery_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> DeliveryEventListResponse:
    service = DeliveryService(db)
    events = await service.events(
        current_user.organization_id, delivery_id, limit=limit, offset=offset
    )
    return DeliveryEventListResponse(
        items=[DeliveryEventRead.model_validate(e) for e in events], total=len(events)
    )


@router.post(
    "/{delivery_id}/retry",
    response_model=DeliveryRead,
    summary="Manually retry a failed or cancelled delivery",
    dependencies=[_manage],
)
async def retry_delivery(
    delivery_id: uuid.UUID,
    body: DeliveryRetry,
    db: DbSession,
    current_user: CurrentUser,
) -> DeliveryRead:
    service = DeliveryService(db)
    delivery = await service.retry(current_user.organization_id, delivery_id)
    return DeliveryRead.model_validate(delivery)


@router.post(
    "/{delivery_id}/cancel",
    response_model=DeliveryRead,
    summary="Cancel a queued or processing delivery",
    dependencies=[_manage],
)
async def cancel_delivery(
    delivery_id: uuid.UUID,
    body: DeliveryCancel,
    db: DbSession,
    current_user: CurrentUser,
) -> DeliveryRead:
    service = DeliveryService(db)
    delivery = await service.cancel(
        current_user.organization_id,
        delivery_id,
        cancelled_by_user_id=current_user.id,
    )
    return DeliveryRead.model_validate(delivery)
