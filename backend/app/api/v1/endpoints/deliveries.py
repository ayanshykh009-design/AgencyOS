"""Delivery endpoints: outbox management + timeline + monitoring.

All endpoints are JWT-authenticated. Reads require ``delivery_read``; writes
require ``delivery_write``; admin actions require ``delivery_manage``.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, DbSession
from app.core.errors import AppError
from app.core.permissions import Permission, require_permission
from app.core.url_validation import is_safe_app_relative_url
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
    # Trust boundary: in-app (dashboard) deliveries materialize as
    # notification inbox rows whose type (SYSTEM / APPROVAL_REQUEST / agent /
    # workflow) and content come from the delivery payload. Only the trusted
    # internal path (delivery worker, services) may enqueue them; a JWT user
    # enqueuing one could fabricate a privileged notification in another
    # user's inbox. Other channels are not shipped yet and fail closed in the
    # service.
    if body.channel is DeliveryChannel.DASHBOARD:
        raise AppError(
            code="delivery.channel_trusted_only",
            message="In-app deliveries are enqueued by trusted internal paths only",
            status_code=403,
        )
    # Trust boundary: the recipient is server-authoritative. An ordinary
    # authenticated client may only enqueue for *itself*.
    if body.recipient_user_id is not None and body.recipient_user_id != current_user.id:
        raise AppError(
            code="delivery.recipient_not_allowed",
            message="Deliveries can only be enqueued for the requesting user",
            status_code=403,
        )
    # Trust boundary: action_url must be an application-relative path, so a
    # client-crafted link can never point outside the app (javascript:,
    # https://attacker, protocol-relative //host, backslash or encoded
    # variants).
    if body.action_url is not None and not is_safe_app_relative_url(body.action_url):
        raise AppError(
            code="delivery.unsafe_action_url",
            message="action_url must be an application-relative path",
            status_code=422,
        )
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
