"""DeliveryRepository — org-scoped delivery outbox CRUD + worker queue ops.

State transitions are guarded single-statement UPDATEs (optimistic, like the
execution queue): a concurrent worker or cancel can never clobber a
transition, and callers receive the updated row or ``None``.

State machine (see ``DeliveryStatus``):

  queued -> processing -> delivered | failed | cancelled
           (processing -> retrying -> queued | cancelled)
  failed/cancelled -> queued only via an explicit manual retry

Cooperative cancellation: a PROCESSING delivery is only flagged
(``cancel_requested_at``); the worker honours the flag once the provider
returns (a successful send always wins).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, cast

from sqlalchemy import func, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.delivery import Delivery
from app.models.enums import DeliveryChannel, DeliveryStatus
from app.repositories.base import TenantRepository

if TYPE_CHECKING:
    pass

_DEFAULT_PAGE_SIZE = 100
_MAX_PAGE_SIZE = 500

DeliveryList = list[Delivery]
DeliveryOrgList = list[uuid.UUID]

_ACTIVE_STATUSES = (
    DeliveryStatus.QUEUED,
    DeliveryStatus.PROCESSING,
    DeliveryStatus.RETRYING,
)

_TERMINAL_RETRYABLE_STATUSES = (DeliveryStatus.FAILED, DeliveryStatus.CANCELLED)


class DeliveryRepository(TenantRepository[Delivery]):
    """Data access for the delivery outbox."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Delivery)

    # -- reads ---------------------------------------------------------

    async def list(
        self,
        organization_id: uuid.UUID,
        *,
        status: DeliveryStatus | None = None,
        channel: DeliveryChannel | None = None,
        recipient_user_id: uuid.UUID | None = None,
        limit: int = _DEFAULT_PAGE_SIZE,
        offset: int = 0,
    ) -> DeliveryList:
        stmt = select(Delivery).where(Delivery.organization_id == organization_id)
        if status is not None:
            stmt = stmt.where(Delivery.status == status)
        if channel is not None:
            stmt = stmt.where(Delivery.channel == channel)
        if recipient_user_id is not None:
            stmt = stmt.where(Delivery.recipient_user_id == recipient_user_id)
        stmt = (
            stmt.order_by(Delivery.created_at.desc())
            .limit(min(limit, _MAX_PAGE_SIZE))
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_pending(self, organization_id: uuid.UUID) -> int:
        """Count un-drained deliveries for an org (QUEUED + PROCESSING + RETRYING).

        Backs the per-org pending cap (``DELIVERY_MAX_PENDING_PER_ORG``).
        """
        stmt = (
            select(func.count(Delivery.id))
            .where(
                Delivery.organization_id == organization_id,
                Delivery.status.in_(_ACTIVE_STATUSES),
            )
            .select_from(Delivery)
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def get_by_idempotency(
        self, organization_id: uuid.UUID, idempotency_key: str
    ) -> Delivery | None:
        """Return the existing delivery for ``(org, idempotency_key)`` or None."""
        stmt = select(Delivery).where(
            Delivery.organization_id == organization_id,
            Delivery.idempotency_key == idempotency_key,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def count_by_status(self) -> dict[str, int]:
        """Global counts by status (platform monitoring, not tenant-scoped)."""
        stmt = select(Delivery.status, func.count(Delivery.id)).group_by(
            Delivery.status
        )
        result = await self._session.execute(stmt)
        return {status.value: count for status, count in result.all()}

    # -- queue operations ------------------------------------------------

    async def get_queued_orgs(self, limit: int) -> DeliveryOrgList:
        """Fair-drain candidates: orgs with queued work, oldest-first."""
        stmt = (
            select(Delivery.organization_id)
            .where(Delivery.status == DeliveryStatus.QUEUED)
            .group_by(Delivery.organization_id)
            .order_by(func.min(Delivery.scheduled_for))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_queued_for_org(
        self, organization_id: uuid.UUID, limit: int
    ) -> DeliveryList:
        """Get the oldest due QUEUED deliveries for one organization."""
        now = datetime.now().astimezone()
        stmt = (
            select(Delivery)
            .where(
                Delivery.organization_id == organization_id,
                Delivery.status == DeliveryStatus.QUEUED,
                Delivery.scheduled_for <= now,
                or_(
                    Delivery.next_attempt_at.is_(None),
                    Delivery.next_attempt_at <= now,
                ),
            )
            .order_by(Delivery.scheduled_for)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def requeue_due_retrying(self, *, limit: int) -> int:
        """Promote due RETRYING rows back to QUEUED (global).

        RETRYING rows wait on ``next_attempt_at`` backoff; once due they
        re-enter the normal drain queue without consuming another attempt.
        """
        now = datetime.now().astimezone()
        stmt = (
            update(Delivery)
            .where(
                Delivery.status == DeliveryStatus.RETRYING,
                Delivery.next_attempt_at.is_not(None),
                Delivery.next_attempt_at <= now,
            )
            .values(
                status=DeliveryStatus.QUEUED,
                next_attempt_at=None,
            )
        )
        result = cast(CursorResult, await self._session.execute(stmt))
        return result.rowcount or 0

    # Guarded state transitions (optimistic; see class docstring).

    async def claim(
        self, organization_id: uuid.UUID, delivery_id: uuid.UUID
    ) -> Delivery | None:
        """QUEUED + due -> PROCESSING, attempts bumped. Returns row or None."""
        now = datetime.now().astimezone()
        stmt = (
            update(Delivery)
            .where(
                Delivery.organization_id == organization_id,
                Delivery.id == delivery_id,
                Delivery.status == DeliveryStatus.QUEUED,
                Delivery.scheduled_for <= now,
                or_(
                    Delivery.next_attempt_at.is_(None),
                    Delivery.next_attempt_at <= now,
                ),
            )
            .values(
                status=DeliveryStatus.PROCESSING,
                attempts=Delivery.attempts + 1,
                next_attempt_at=None,
                attempt_started_at=now,
                last_error=None,
            )
            .returning(Delivery)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_delivered(
        self,
        organization_id: uuid.UUID,
        delivery_id: uuid.UUID,
        *,
        provider_metadata: dict,
        delivered_at: datetime,
    ) -> Delivery | None:
        """PROCESSING -> DELIVERED (terminal). Returns row or None."""
        stmt = (
            update(Delivery)
            .where(
                Delivery.organization_id == organization_id,
                Delivery.id == delivery_id,
                Delivery.status == DeliveryStatus.PROCESSING,
            )
            .values(
                status=DeliveryStatus.DELIVERED,
                delivered_at=delivered_at,
                next_attempt_at=None,
                attempt_started_at=None,
                cancel_requested_at=None,
                cancelled_by_user_id=None,
                last_error=None,
                provider_metadata=provider_metadata,
            )
            .returning(Delivery)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_failed(
        self,
        organization_id: uuid.UUID,
        delivery_id: uuid.UUID,
        *,
        error: str,
        failed_at: datetime,
    ) -> Delivery | None:
        """PROCESSING -> FAILED (terminal, attempts exhausted or permanent)."""
        stmt = (
            update(Delivery)
            .where(
                Delivery.organization_id == organization_id,
                Delivery.id == delivery_id,
                Delivery.status == DeliveryStatus.PROCESSING,
            )
            .values(
                status=DeliveryStatus.FAILED,
                failed_at=failed_at,
                next_attempt_at=None,
                attempt_started_at=None,
                cancel_requested_at=None,
                cancelled_by_user_id=None,
                last_error=error,
            )
            .returning(Delivery)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def schedule_retry(
        self,
        organization_id: uuid.UUID,
        delivery_id: uuid.UUID,
        *,
        next_attempt_at: datetime,
        error: str,
    ) -> Delivery | None:
        """PROCESSING -> RETRYING (backoff wait; attempts preserved)."""
        stmt = (
            update(Delivery)
            .where(
                Delivery.organization_id == organization_id,
                Delivery.id == delivery_id,
                Delivery.status == DeliveryStatus.PROCESSING,
            )
            .values(
                status=DeliveryStatus.RETRYING,
                next_attempt_at=next_attempt_at,
                attempt_started_at=None,
                last_error=error,
            )
            .returning(Delivery)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_cancel_requested(
        self,
        organization_id: uuid.UUID,
        delivery_id: uuid.UUID,
        *,
        cancel_requested_at: datetime,
        cancelled_by_user_id: uuid.UUID | None,
    ) -> Delivery | None:
        """PROCESSING: flag a cooperative cancellation (non-terminal)."""
        stmt = (
            update(Delivery)
            .where(
                Delivery.organization_id == organization_id,
                Delivery.id == delivery_id,
                Delivery.status == DeliveryStatus.PROCESSING,
                Delivery.cancel_requested_at.is_(None),
            )
            .values(
                cancel_requested_at=cancel_requested_at,
                cancelled_by_user_id=cancelled_by_user_id,
            )
            .returning(Delivery)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_cancelled(
        self,
        organization_id: uuid.UUID,
        delivery_id: uuid.UUID,
        *,
        cancelled_at: datetime,
        cancelled_by_user_id: uuid.UUID | None = None,
    ) -> Delivery | None:
        """QUEUED/RETRYING -> CANCELLED (terminal, immediate)."""
        stmt = (
            update(Delivery)
            .where(
                Delivery.organization_id == organization_id,
                Delivery.id == delivery_id,
                Delivery.status.in_((DeliveryStatus.QUEUED, DeliveryStatus.RETRYING)),
            )
            .values(
                status=DeliveryStatus.CANCELLED,
                cancelled_at=cancelled_at,
                cancelled_by_user_id=cancelled_by_user_id,
                next_attempt_at=None,
                attempt_started_at=None,
            )
            .returning(Delivery)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_cancelled_after_send(
        self,
        organization_id: uuid.UUID,
        delivery_id: uuid.UUID,
        *,
        cancelled_at: datetime,
        error: str | None,
    ) -> Delivery | None:
        """PROCESSING with a cancel request -> CANCELLED (worker honours flag).

        Only fires when the provider did NOT deliver (delivered always wins
        over a cancel request).
        """
        stmt = (
            update(Delivery)
            .where(
                Delivery.organization_id == organization_id,
                Delivery.id == delivery_id,
                Delivery.status == DeliveryStatus.PROCESSING,
                Delivery.cancel_requested_at.is_not(None),
            )
            .values(
                status=DeliveryStatus.CANCELLED,
                cancelled_at=cancelled_at,
                next_attempt_at=None,
                attempt_started_at=None,
                last_error=error,
            )
            .returning(Delivery)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_requeued(
        self,
        organization_id: uuid.UUID,
        delivery_id: uuid.UUID,
        *,
        requeued_at: datetime,
    ) -> Delivery | None:
        """FAILED/CANCELLED -> QUEUED (manual retry, fresh attempt budget)."""
        stmt = (
            update(Delivery)
            .where(
                Delivery.organization_id == organization_id,
                Delivery.id == delivery_id,
                Delivery.status.in_(_TERMINAL_RETRYABLE_STATUSES),
            )
            .values(
                status=DeliveryStatus.QUEUED,
                attempts=0,
                next_attempt_at=requeued_at,
                attempt_started_at=None,
                cancel_requested_at=None,
                cancelled_by_user_id=None,
                delivered_at=None,
                failed_at=None,
                cancelled_at=None,
                last_error=None,
            )
            .returning(Delivery)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    # -- stale-processing recovery ----------------------------------------

    async def list_stale_processing(self, before: datetime, limit: int) -> DeliveryList:
        """PROCESSING rows stuck past the recovery window (or never started).

        Rows without ``attempt_started_at`` (legacy crash before the claim
        stamp) fall back to ``updated_at`` so they are still recovered.
        """
        stmt = (
            select(Delivery)
            .where(
                Delivery.status == DeliveryStatus.PROCESSING,
                or_(
                    Delivery.attempt_started_at.is_(None),
                    Delivery.attempt_started_at < before,
                    Delivery.updated_at < before,
                ),
            )
            .order_by(Delivery.updated_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def requeue_stale(
        self, organization_id: uuid.UUID, delivery_id: uuid.UUID
    ) -> Delivery | None:
        """PROCESSING -> QUEUED (recovery; attempt budget preserved)."""
        stmt = (
            update(Delivery)
            .where(
                Delivery.organization_id == organization_id,
                Delivery.id == delivery_id,
                Delivery.status == DeliveryStatus.PROCESSING,
            )
            .values(
                status=DeliveryStatus.QUEUED,
                next_attempt_at=datetime.now().astimezone(),
                attempt_started_at=None,
            )
            .returning(Delivery)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def release_stale_processing(self, before: datetime) -> int:
        """Bulk requeue of stale PROCESSING rows (legacy path, no events).

        Prefer :meth:`list_stale_processing` + :meth:`requeue_stale` so the
        worker can append ``recovery_guard``/``timed_out`` events per row.
        """
        rows = await self.list_stale_processing(before, limit=500)
        requeued = 0
        for row in rows:
            if await self.requeue_stale(row.organization_id, row.id):
                requeued += 1
        return requeued
