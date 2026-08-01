"""Dashboard service: aggregates repository data for the UI."""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import LeadStatus
from app.repositories.activity_log import ActivityLogRepository
from app.repositories.conversation import ConversationRepository
from app.repositories.import_job import ImportJobRepository
from app.repositories.lead import LeadRepository
from app.repositories.outreach import OutreachAttemptRepository
from app.repositories.provider_usage import ProviderUsageRepository
from app.repositories.user import UserRepository


class DashboardService:
    """Composes repository queries into a dashboard summary."""

    def __init__(self, session: AsyncSession) -> None:
        self._leads = LeadRepository(session)
        self._users = UserRepository(session)
        self._conversations = ConversationRepository(session)
        self._imports = ImportJobRepository(session)
        self._attempts = OutreachAttemptRepository(session)
        self._logs = ActivityLogRepository(session)
        self._usage = ProviderUsageRepository(session)

    async def summary(self, organization_id: uuid.UUID) -> dict:
        """Return the aggregate snapshot used by the dashboard landing page."""
        funnel = await self._leads.funnel(organization_id)
        total_leads = sum(funnel.values())
        status_counts = {status.value: funnel.get(status, 0) for status in LeadStatus}
        status_counts["total"] = total_leads

        return {
            "leads": status_counts,
            "users": {
                "total": await self._users.count_by_org(organization_id),
                "active": await self._users.count_active_by_org(organization_id),
            },
            "conversations": {
                "open": await self._conversations.count_open(organization_id),
            },
            "outreach": {
                "outstanding": await self._attempts.count_outstanding(organization_id),
            },
            "imports": {
                "active": await self._imports.count_active(organization_id),
            },
            "activity": {
                "recent": await self._logs.list(organization_id, limit=10),
            },
            "usage": {
                "spend_last_30_days_usd": await self._usage.spend_last_30_days(
                    organization_id
                ),
            },
        }
