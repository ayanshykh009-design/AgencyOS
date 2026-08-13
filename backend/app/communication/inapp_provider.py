"""In-app (dashboard) delivery provider (M6).

Creates a per-user ``notifications`` inbox row for the delivery message. The
transaction boundary makes the send idempotent: the notification insert and
the delivery ``DELIVERED`` transition commit together, so a worker crash rolls
both back and the recovery re-send creates exactly one inbox row.
"""

from __future__ import annotations

import logging

from app.communication.contract import (
    DeliveryMessage,
    DeliveryProvider,
    DeliveryResult,
)
from app.models.enums import DeliveryChannel, NotificationType

logger = logging.getLogger("agencyos.communication.provider")


class InAppProvider(DeliveryProvider):
    """Delivers to the dashboard by creating a per-user notification row."""

    channel = DeliveryChannel.DASHBOARD

    async def deliver(self, message: DeliveryMessage) -> DeliveryResult:
        from app.models.notification import Notification

        ntype = self._notification_type(message)
        notification = Notification(
            organization_id=message.organization_id,
            user_id=message.recipient_user_id,
            type=ntype,
            title=message.subject,
            body=message.body,
            action_url=message.action_url,
            metadata_={
                **message.metadata,
                "delivery_id": str(message.delivery_id),
            },
        )
        self._session.add(notification)
        await self._session.flush()
        logger.info(
            "dashboard delivery %s -> notification %s",
            message.delivery_id,
            notification.id,
        )
        return DeliveryResult(
            ok=True,
            provider_metadata={
                "notification_id": str(notification.id),
                "notification_type": ntype.value,
            },
        )

    @staticmethod
    def _notification_type(message: DeliveryMessage) -> NotificationType:
        if (message.metadata or {}).get("approval_request_id") is not None:
            return NotificationType.APPROVAL_REQUEST
        hint = (message.metadata or {}).get("notification_type")
        try:
            return NotificationType(hint) if hint else NotificationType.SYSTEM
        except ValueError:
            return NotificationType.SYSTEM
