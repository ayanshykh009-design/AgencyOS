"""ApprovalLog repository (immutable approval audit trail).

Append-only: rows are created and queried, never updated or deleted.
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval_log import ApprovalLog
from app.repositories.base import TenantRepository

if TYPE_CHECKING:
    pass


class ApprovalLogRepository(TenantRepository[ApprovalLog]):
    """Data access for the immutable approval audit log."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ApprovalLog)

    async def list_by_request(
        self,
        organization_id: uuid.UUID,
        approval_request_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ApprovalLog]:
        """Timeline for one approval request, oldest first."""
        stmt = (
            select(ApprovalLog)
            .where(
                ApprovalLog.organization_id == organization_id,
                ApprovalLog.approval_request_id == approval_request_id,
            )
            .order_by(ApprovalLog.occurred_at.asc())
            .limit(min(limit, 200))
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_request(
        self, organization_id: uuid.UUID, approval_request_id: uuid.UUID
    ) -> int:
        stmt = (
            select(func.count(ApprovalLog.id))
            .where(
                ApprovalLog.organization_id == organization_id,
                ApprovalLog.approval_request_id == approval_request_id,
            )
            .select_from(ApprovalLog)
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())
