"""Notification service: per-user in-app inbox.

Thin orchestration over the M2 repository. The actual notification delivery
(worker) lands in M6; this service only records and reads inbox rows.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.enums import NotificationType
from app.models.notification import Notification
from app.repositories.notification import NotificationRepository
from app.services.base import commit_with_retry


class NotificationService:
    """Owns the in-app notification inbox and its transaction boundary."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._notifications = NotificationRepository(session)

    async def list_for_user(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        only_unread: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Notification]:
        return await self._notifications.list_for_user(
            organization_id, user_id, only_unread=only_unread, limit=limit, offset=offset
        )

    async def get_for_user(
        self, organization_id: uuid.UUID, user_id: uuid.UUID, notification_id: uuid.UUID
    ) -> Notification:
        """Return a notification owned by ``user_id`` (else 404)."""
        notification = await self._notifications.get(organization_id, notification_id)
        if notification is None or notification.user_id != user_id:
            raise AppError(
                code="notification.not_found",
                message="Notification not found",
                status_code=404,
            )
        return notification

    async def unread_count(
        self, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> int:
        return await self._notifications.count_unread(organization_id, user_id)

    async def counts_by_type(self, organization_id: uuid.UUID) -> dict[NotificationType, int]:
        return await self._notifications.count_by_type(organization_id)

    async def set_read(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        notification_id: uuid.UUID,
        *,
        is_read: bool = True,
    ) -> Notification:
        """Mark read/unread; 404 when not found or not owned by the user."""
        if not await self._notifications.set_read(
            organization_id, user_id, notification_id, is_read=is_read
        ):
            raise AppError(
                code="notification.not_found",
                message="Notification not found",
                status_code=404,
            )
        await commit_with_retry(self._session)
        return await self.get_for_user(organization_id, user_id, notification_id)

    async def create(
        self,
        organization_id: uuid.UUID,
        *,
        user_id: uuid.UUID | None = None,
        type: NotificationType,
        title: str,
        body: str,
        action_url: str | None,
        metadata_: dict[str, Any],
    ) -> Notification:
        notification = Notification(
            organization_id=organization_id,
            user_id=user_id,
            type=type,
            title=title,
            body=body,
            action_url=action_url,
            metadata_=metadata_,
        )
        self._notifications.add(notification)
        await commit_with_retry(self._session)
        return notification
