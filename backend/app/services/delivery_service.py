"""DeliveryService: enqueue, query, retry, cancel, timeline.

Thin orchestration over repositories; owns the transaction boundary.
Workers call the guarded transitions (claim, mark_delivered, etc.) via
this service to keep the transaction semantics in one place.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.core.metrics import get_counter
from app.models.delivery import Delivery
from app.models.delivery_event import DeliveryEvent
from app.models.enums import DeliveryChannel, DeliveryEventType, DeliveryStatus
from app.repositories.delivery import DeliveryRepository
from app.repositories.delivery_event import DeliveryEventRepository
from app.services.base import commit_with_retry, utcnow

logger = logging.getLogger("agencyos.communication.delivery")

# Statuses a caller can request cancellation for (immediate, no provider in flight).
_IMMEDIATELY_CANCELLABLE = (DeliveryStatus.QUEUED, DeliveryStatus.RETRYING)


class DeliveryService:
    """Owns the delivery outbox and its transaction boundary."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._deliveries = DeliveryRepository(session)
        self._events = DeliveryEventRepository(session)

    # -- reads ---------------------------------------------------------

    async def list_deliveries(
        self,
        organization_id: uuid.UUID,
        *,
        status: DeliveryStatus | None = None,
        channel: DeliveryChannel | None = None,
        recipient_user_id: uuid.UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Delivery]:
        return await self._deliveries.list_deliveries(
            organization_id,
            status=status,
            channel=channel,
            recipient_user_id=recipient_user_id,
            limit=limit,
            offset=offset,
        )

    async def get(self, organization_id: uuid.UUID, delivery_id: uuid.UUID) -> Delivery:
        delivery = await self._deliveries.get(organization_id, delivery_id)
        if delivery is None:
            raise AppError(
                code="delivery.not_found",
                message="Delivery not found",
                status_code=404,
            )
        return delivery

    async def events(
        self,
        organization_id: uuid.UUID,
        delivery_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[DeliveryEvent]:
        return await self._events.list_by_delivery(
            organization_id, delivery_id, limit=limit, offset=offset
        )

    async def statistics(self, organization_id: uuid.UUID) -> dict[str, Any]:
        """Return delivery statistics for one organization."""
        stmt = (
            select(Delivery.status, func.count(Delivery.id))
            .where(Delivery.organization_id == organization_id)
            .group_by(Delivery.status)
        )
        result = await self._session.execute(stmt)
        counts = {status.value: count for status, count in result.all()}

        queued = counts.get("queued", 0)
        processing = counts.get("processing", 0)
        retrying = counts.get("retrying", 0)
        delivered = counts.get("delivered", 0)
        failed = counts.get("failed", 0)
        cancelled = counts.get("cancelled", 0)

        pending = queued + processing + retrying
        cap = settings.DELIVERY_MAX_PENDING_PER_ORG
        utilization = (pending / cap * 100) if cap > 0 else 0.0

        return {
            "queued": queued,
            "processing": processing,
            "retrying": retrying,
            "delivered": delivered,
            "failed": failed,
            "cancelled": cancelled,
            "pending_cap_utilization_pct": round(utilization, 2),
        }

    async def platform_statistics(self) -> dict[str, Any]:
        """Global delivery statistics across all organizations (monitoring)."""
        counts = await self._deliveries.count_by_status()
        queued = counts.get("queued", 0)
        processing = counts.get("processing", 0)
        retrying = counts.get("retrying", 0)
        return {
            "queued": queued,
            "processing": processing,
            "retrying": retrying,
            "delivered": counts.get("delivered", 0),
            "failed": counts.get("failed", 0),
            "cancelled": counts.get("cancelled", 0),
            "active": queued + processing + retrying,
            "terminal": counts.get("delivered", 0)
            + counts.get("failed", 0)
            + counts.get("cancelled", 0),
        }

    # -- enqueue -------------------------------------------------------

    async def enqueue(
        self,
        organization_id: uuid.UUID,
        *,
        channel: DeliveryChannel,
        recipient_user_id: uuid.UUID | None = None,
        notification_id: uuid.UUID | None = None,
        approval_request_id: uuid.UUID | None = None,
        subject: str,
        body: str,
        action_url: str | None = None,
        payload: dict[str, Any] | None = None,
        max_attempts: int | None = None,
        scheduled_for: datetime | None = None,
        idempotency_key: str | None = None,
    ) -> Delivery:
        """Add a delivery to the outbox (idempotent on idempotency_key).

        - fail closed for unshipped channels (email/whatsapp/push)
        - enforces the per-org pending cap (``delivery.pending_cap_exceeded``)
        - rejects oversized payloads (``delivery.payload_too_large``)
        - the DB partial unique index is authoritative: a concurrent duplicate
          insert surfaces as ``delivery.duplicate_idempotency_key``.
        """
        from app.communication.providers import provider_available

        if not provider_available(channel):
            raise AppError(
                code="provider.not_configured",
                message=f"No provider shipped for channel '{channel.value}'",
                status_code=422,
            )

        payload = payload or {}
        if self._payload_too_large(payload):
            raise AppError(
                code="delivery.payload_too_large",
                message="Delivery payload exceeds the maximum allowed size",
                status_code=422,
            )

        # Idempotency: if key provided and exists, return existing delivery.
        if idempotency_key:
            existing = await self._deliveries.get_by_idempotency(organization_id, idempotency_key)
            if existing:
                return existing

        # Pending cap (per org) - fail closed before insert.
        max_pending = settings.DELIVERY_MAX_PENDING_PER_ORG
        if max_pending and max_pending > 0:
            pending = await self._deliveries.count_pending(organization_id)
            if pending >= max_pending:
                raise AppError(
                    code="delivery.pending_cap_exceeded",
                    message=f"Per-org pending cap ({max_pending}) exceeded",
                    status_code=429,
                )

        now = utcnow()
        delivery = Delivery(
            organization_id=organization_id,
            channel=channel,
            recipient_user_id=recipient_user_id,
            notification_id=notification_id,
            approval_request_id=approval_request_id,
            subject=subject,
            body=body,
            action_url=action_url,
            status=DeliveryStatus.QUEUED,
            attempts=0,
            max_attempts=max_attempts or settings.DELIVERY_MAX_ATTEMPTS,
            next_attempt_at=scheduled_for or now,
            provider_metadata={},
            payload=payload,
            idempotency_key=idempotency_key,
            scheduled_for=scheduled_for or now,
        )
        self._deliveries.add(delivery)

        # Initial queued event.
        self._events.add(
            DeliveryEvent(
                organization_id=organization_id,
                delivery_id=delivery.id,
                event_type=DeliveryEventType.QUEUED,
                attempt=0,
                metadata_={"idempotency_key": idempotency_key} if idempotency_key else {},
            )
        )

        try:
            await commit_with_retry(self._session)
        except IntegrityError as exc:
            await self._session.rollback()
            if idempotency_key:
                # Concurrent duplicate: the unique index is authoritative.
                raise AppError(
                    code="delivery.duplicate_idempotency_key",
                    message="A delivery with this idempotency key already exists",
                    status_code=409,
                ) from exc
            raise

        get_counter(
            "delivery_queued_total",
            description="Deliveries enqueued into the outbox",
        ).add(1, {"channel": channel.value})
        logger.info(
            "delivery %s enqueued for org %s via %s",
            delivery.id,
            organization_id,
            channel,
        )
        return delivery

    # -- cancel / retry (manual) ---------------------------------------

    async def cancel(
        self,
        organization_id: uuid.UUID,
        delivery_id: uuid.UUID,
        *,
        cancelled_by_user_id: uuid.UUID | None = None,
    ) -> Delivery:
        delivery = await self.get(organization_id, delivery_id)
        now = utcnow()

        if delivery.status in _IMMEDIATELY_CANCELLABLE:
            cancelled = await self._deliveries.mark_cancelled(
                organization_id,
                delivery_id,
                cancelled_at=now,
                cancelled_by_user_id=cancelled_by_user_id,
            )
            if cancelled:
                self._events.add(
                    DeliveryEvent(
                        organization_id=organization_id,
                        delivery_id=delivery_id,
                        event_type=DeliveryEventType.CANCELLED,
                        attempt=delivery.attempts,
                        metadata_={},
                    )
                )
                await commit_with_retry(self._session)
                return cancelled
            # Guarded update matched nothing: the row changed concurrently
            # (e.g. a worker claimed it). Return the fresh state instead of None.
            return await self.get(organization_id, delivery_id)

        if delivery.status == DeliveryStatus.PROCESSING:
            # Cooperative: flag the row; the worker honours it once the
            # provider returns (a successful send always wins).
            flagged = await self._deliveries.mark_cancel_requested(
                organization_id,
                delivery_id,
                cancel_requested_at=now,
                cancelled_by_user_id=cancelled_by_user_id,
            )
            if flagged:
                await commit_with_retry(self._session)
                return flagged
            # State changed concurrently (already cancelled/terminal).
            return await self.get(organization_id, delivery_id)

        raise AppError(
            code="delivery.invalid_state",
            message=f"Cannot cancel a {delivery.status.value} delivery",
            status_code=409,
        )

    async def retry(self, organization_id: uuid.UUID, delivery_id: uuid.UUID) -> Delivery:
        delivery = await self.get(organization_id, delivery_id)
        if delivery.status not in (
            DeliveryStatus.FAILED,
            DeliveryStatus.CANCELLED,
        ):
            raise AppError(
                code="delivery.invalid_state",
                message=f"Cannot retry a {delivery.status.value} delivery",
                status_code=409,
            )
        now = utcnow()
        requeued = await self._deliveries.mark_requeued(
            organization_id, delivery_id, requeued_at=now
        )
        if requeued:
            self._events.add(
                DeliveryEvent(
                    organization_id=organization_id,
                    delivery_id=delivery_id,
                    event_type=DeliveryEventType.QUEUED,
                    attempt=0,
                    metadata_={"manual_retry": True},
                )
            )
            await commit_with_retry(self._session)
            return requeued
        # Guarded update matched nothing: state changed concurrently.
        return await self.get(organization_id, delivery_id)

    @staticmethod
    def _payload_too_large(payload: dict[str, Any]) -> bool:
        limit = settings.DELIVERY_MAX_PAYLOAD_BYTES
        if limit <= 0:
            return False
        return len(json.dumps(payload, default=str).encode("utf-8")) > limit
