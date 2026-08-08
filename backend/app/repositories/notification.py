"""Notification repository (in-app inbox).

Rows are pruned after ``NOTIFICATION_RETENTION_DAYS`` by the retention sweep.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, cast

from sqlalchemy import delete, func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import NotificationType
from app.models.notification import Notification
from app.repositories.base import TenantRepository

if TYPE_CHECKING:
    pass


class NotificationRepository(TenantRepository[Notification]):
    """Data access for in-app notifications (org-scoped)."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Notification)

    async def list_for_user(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        only_unread: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Notification]:
        """List a user's inbox, newest first, optionally unread-only."""
        stmt = select(Notification).where(
            Notification.organization_id == organization_id,
            Notification.user_id == user_id,
        )
        if only_unread:
            stmt = stmt.where(Notification.is_read.is_(False))
        stmt = stmt.order_by(Notification.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_unread(
        self, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> int:
        """Unread badge count for a user within an organization."""
        stmt = (
            select(func.count(Notification.id))
            .where(
                Notification.organization_id == organization_id,
                Notification.user_id == user_id,
                Notification.is_read.is_(False),
            )
            .select_from(Notification)
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def set_read(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        notification_id: uuid.UUID,
        *,
        is_read: bool,
    ) -> bool:
        """Mark one notification read/unread; returns False when not found."""
        stmt = (
            update(Notification)
            .where(
                Notification.organization_id == organization_id,
                Notification.user_id == user_id,
                Notification.id == notification_id,
            )
            .values(
                is_read=is_read,
                read_at=datetime.now().astimezone() if is_read else None,
            )
        )
        result = cast(CursorResult, await self._session.execute(stmt))
        return (result.rowcount or 0) > 0

    async def mark_read(
        self, organization_id: uuid.UUID, user_id: uuid.UUID, notification_id: uuid.UUID
    ) -> bool:
        """Mark one notification read; returns False when it does not exist."""
        return await self.set_read(
            organization_id, user_id, notification_id, is_read=True
        )

    async def count_by_type(
        self, organization_id: uuid.UUID
    ) -> dict[NotificationType, int]:
        """Notification counts grouped by type."""
        stmt = (
            select(Notification.type, func.count(Notification.id))
            .where(Notification.organization_id == organization_id)
            .group_by(Notification.type)
        )
        result = await self._session.execute(stmt)
        return {ntype: int(count) for ntype, count in result.all()}

    async def delete_older_than(self, cutoff: datetime, batch: int) -> int:
        """Prune at most ``batch`` notifications older than ``cutoff`` (retention)."""
        subq = (
            select(Notification.id)
            .where(Notification.created_at < cutoff)
            .order_by(Notification.created_at)
            .limit(max(batch, 1))
        )
        stmt = delete(Notification).where(Notification.id.in_(subq))
        result = cast(CursorResult, await self._session.execute(stmt))
        return result.rowcount or 0
