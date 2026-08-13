"""Founder service: generated briefings + business insights.

Thin orchestration over the M2 repositories. *Generation* of insights/briefings
(by the growth/insight agent) lands in M7; this service only creates, reads,
updates, and deletes the curated artifacts.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.briefing import Briefing
from app.models.business_insight import BusinessInsight
from app.models.enums import BriefingType
from app.repositories.briefing import BriefingRepository
from app.repositories.business_insight import BusinessInsightRepository
from app.services.base import commit_with_retry


class FounderService:
    """Owns founder-facing artifacts and the transaction boundary."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._briefings = BriefingRepository(session)
        self._insights = BusinessInsightRepository(session)

    # -- briefings ------------------------------------------------------

    async def list_briefings(
        self,
        organization_id: uuid.UUID,
        *,
        briefing_type: BriefingType | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Briefing]:
        return await self._briefings.list_by_type(
            organization_id, briefing_type=briefing_type, limit=limit, offset=offset
        )

    async def latest_briefing(
        self, organization_id: uuid.UUID, briefing_type: BriefingType
    ) -> Briefing:
        briefing = await self._briefings.latest_by_type(organization_id, briefing_type)
        if briefing is None:
            raise AppError(
                code="briefing.not_found",
                message="Briefing not found",
                status_code=404,
            )
        return briefing

    async def get_briefing(self, organization_id: uuid.UUID, briefing_id: uuid.UUID) -> Briefing:
        return await self._briefings.get_or_404(organization_id, briefing_id)

    async def create_briefing(
        self,
        organization_id: uuid.UUID,
        *,
        briefing_type: BriefingType,
        title: str,
        summary: str,
        sections: list[dict[str, Any]],
        metadata_: dict[str, Any],
    ) -> Briefing:
        briefing = Briefing(
            organization_id=organization_id,
            briefing_type=briefing_type,
            title=title,
            summary=summary,
            sections=sections,
            metadata_=metadata_,
        )
        self._briefings.add(briefing)
        await commit_with_retry(self._session)
        return briefing

    # -- insights -------------------------------------------------------

    async def list_insights(
        self,
        organization_id: uuid.UUID,
        *,
        status: Any = None,
        severity: Any = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[BusinessInsight]:
        return await self._insights.list_by_status(
            organization_id, status=status, severity=severity, limit=limit, offset=offset
        )

    async def get_insight(
        self, organization_id: uuid.UUID, insight_id: uuid.UUID
    ) -> BusinessInsight:
        return await self._insights.get_or_404(organization_id, insight_id)

    async def update_insight(
        self,
        organization_id: uuid.UUID,
        insight_id: uuid.UUID,
        *,
        status: Any = None,
        severity: Any = None,
    ) -> BusinessInsight:
        insight = await self._insights.get_or_404(organization_id, insight_id)
        if status is not None:
            insight.status = status
        if severity is not None:
            insight.severity = severity
        await commit_with_retry(self._session)
        return insight

    async def delete_insight(self, organization_id: uuid.UUID, insight_id: uuid.UUID) -> None:
        if not await self._insights.delete(organization_id, insight_id):
            raise AppError(
                code="business_insight.not_found",
                message="BusinessInsight not found",
                status_code=404,
            )
        await commit_with_retry(self._session)

    async def create_insight(
        self,
        organization_id: uuid.UUID,
        *,
        insight_type: Any,
        severity: Any,
        status: Any,
        title: str,
        summary: str,
        source_table: str | None,
        source_row_id: uuid.UUID | None,
        metadata_: dict[str, Any],
    ) -> BusinessInsight:
        insight = BusinessInsight(
            organization_id=organization_id,
            insight_type=insight_type,
            severity=severity,
            status=status,
            title=title,
            summary=summary,
            source_table=source_table,
            source_row_id=source_row_id,
            metadata_=metadata_,
        )
        self._insights.add(insight)
        await commit_with_retry(self._session)
        return insight

    async def insight_counts(self, organization_id: uuid.UUID) -> tuple[int, dict[Any, int]]:
        open_count = await self._insights.count_open(organization_id)
        by_type = await self._insights.count_by_type(organization_id)
        return open_count, by_type
