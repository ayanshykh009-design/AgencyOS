"""ApprovalRequest repository (gated workflow approvals).

Pending requests auto-expire (deny) at ``expires_at``; the sweep query
returns expired-pending rows for the service to transition and log.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, cast

from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval_request import ApprovalRequest
from app.models.enums import ApprovalRequestStatus
from app.repositories.base import TenantRepository

if TYPE_CHECKING:
    pass


class ApprovalRequestRepository(TenantRepository[ApprovalRequest]):
    """Data access for approval requests (org-scoped)."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ApprovalRequest)

    async def list_by_status(
        self,
        organization_id: uuid.UUID,
        *,
        status: ApprovalRequestStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ApprovalRequest]:
        """List approval requests, optionally filtered by status, newest first."""
        stmt = select(ApprovalRequest).where(
            ApprovalRequest.organization_id == organization_id
        )
        if status is not None:
            stmt = stmt.where(ApprovalRequest.status == status)
        stmt = stmt.order_by(ApprovalRequest.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_pending_expired(
        self, organization_id: uuid.UUID, *, now: datetime, limit: int = 200
    ) -> list[ApprovalRequest]:
        """Pending requests past their expiry (for the expiry sweep)."""
        stmt = (
            select(ApprovalRequest)
            .where(
                ApprovalRequest.organization_id == organization_id,
                ApprovalRequest.status == ApprovalRequestStatus.PENDING,
                ApprovalRequest.expires_at < now,
            )
            .order_by(ApprovalRequest.expires_at)
            .limit(min(limit, 500))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_pending(self, organization_id: uuid.UUID) -> int:
        """Open (pending) approval count."""
        stmt = (
            select(func.count(ApprovalRequest.id))
            .where(
                ApprovalRequest.organization_id == organization_id,
                ApprovalRequest.status == ApprovalRequestStatus.PENDING,
            )
            .select_from(ApprovalRequest)
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def mark_expired(
        self,
        organization_id: uuid.UUID,
        request_id: uuid.UUID,
        *,
        now: datetime,
    ) -> bool:
        """Transition a request to expired; returns False when already decided."""
        stmt = (
            update(ApprovalRequest)
            .where(
                ApprovalRequest.organization_id == organization_id,
                ApprovalRequest.id == request_id,
                ApprovalRequest.status == ApprovalRequestStatus.PENDING,
            )
            .values(status=ApprovalRequestStatus.EXPIRED, decided_at=now)
        )
        result = cast(CursorResult, await self._session.execute(stmt))
        return (result.rowcount or 0) > 0
