"""Communication service: founder communications summary view.

Read-only aggregation over the Phase 5D inbox surfaces (notifications,
approvals, briefings, insights). No AI or delivery logic — this is the
aggregate digest the founder communication layer exposes.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.briefing import Briefing
from app.models.enums import BriefingType
from app.repositories.approval_request import ApprovalRequestRepository
from app.repositories.briefing import BriefingRepository
from app.repositories.business_insight import BusinessInsightRepository
from app.repositories.notification import NotificationRepository


@dataclass(frozen=True)
class CommunicationSummary:
    """Aggregate digest for the current user's communication surfaces."""

    unread_notifications: int
    pending_approvals: int
    active_insights: int
    latest_briefing: Briefing | None


class CommunicationService:
    """Owns the communications summary and its transaction boundary."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._notifications = NotificationRepository(session)
        self._approvals = ApprovalRequestRepository(session)
        self._insights = BusinessInsightRepository(session)
        self._briefings = BriefingRepository(session)

    async def summary(
        self, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> CommunicationSummary:
        return CommunicationSummary(
            unread_notifications=await self._notifications.count_unread(
                organization_id, user_id
            ),
            pending_approvals=await self._approvals.count_pending(organization_id),
            active_insights=await self._insights.count_open(organization_id),
            latest_briefing=await self._briefings.latest_by_type(
                organization_id, BriefingType.DAILY
            ),
        )
