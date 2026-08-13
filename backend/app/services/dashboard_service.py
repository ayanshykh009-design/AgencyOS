"""Dashboard service: aggregates repository data for the UI."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.dashboard import DashboardRepository


class DashboardService:
    """Composes the single-round-trip snapshot into a dashboard summary."""

    def __init__(self, session: AsyncSession) -> None:
        self._dashboard = DashboardRepository(session)

    async def summary(self, organization_id: uuid.UUID) -> dict:
        """Return the aggregate snapshot used by the dashboard landing page.

        All counters are computed by ``DashboardRepository`` in a single SQL
        statement; this method only shapes the result for the response schema.
        """
        now = datetime.now(UTC)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        since_30d = (now - timedelta(days=30)).date()

        snapshot = await self._dashboard.summary_snapshot(
            organization_id,
            now=now,
            start_of_day=start_of_day,
            end_of_day=start_of_day + timedelta(days=1),
            since_30d=since_30d,
        )

        funnel = snapshot["funnel"]
        return {
            "leads": {**funnel, "total": sum(funnel.values())},
            "users": snapshot["users"],
            "conversations": snapshot["conversations"],
            "outreach": snapshot["outreach"],
            "imports": snapshot["imports"],
            "tasks": snapshot["tasks"],
            "pipeline": snapshot["pipeline"],
            "activity": {"recent": snapshot["recent_activity"]},
            "usage": {"spend_last_30_days_usd": snapshot["spend_30d"]},
        }
