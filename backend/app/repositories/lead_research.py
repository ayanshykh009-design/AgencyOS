"""LeadResearch repository: enrichment output (one row per lead)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.lead_research import LeadResearch


class LeadResearchRepository:
    """Data access for ``lead_research`` rows (org-scoped)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, organization_id: uuid.UUID, lead_id: uuid.UUID) -> LeadResearch | None:
        stmt = select(LeadResearch).where(
            LeadResearch.organization_id == organization_id,
            LeadResearch.lead_id == lead_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_404(self, organization_id: uuid.UUID, lead_id: uuid.UUID) -> LeadResearch:
        research = await self.get(organization_id, lead_id)
        if research is None:
            raise AppError(
                code="research.not_found",
                message="Research not found for this lead",
                status_code=404,
            )
        return research

    async def upsert(
        self,
        organization_id: uuid.UUID,
        lead_id: uuid.UUID,
        *,
        status: str = "in_progress",
        company_overview: str | None = None,
        pain_points: list[Any] | None = None,
        tech_stack: list[Any] | None = None,
        recent_news: list[Any] | None = None,
        linkedin_summary: str | None = None,
        icp_match_score: int | None = None,
        raw_data: dict[str, Any] | None = None,
        research_source: str | None = None,
        researched_at: datetime | None = None,
    ) -> LeadResearch:
        """Create-or-update a research row. Returns the live instance."""
        existing = await self.get(organization_id, lead_id)
        if existing is None:
            research = LeadResearch(
                lead_id=lead_id,
                organization_id=organization_id,
                status=status,
                company_overview=company_overview,
                pain_points=pain_points or [],
                tech_stack=tech_stack or [],
                recent_news=recent_news or [],
                linkedin_summary=linkedin_summary,
                icp_match_score=icp_match_score,
                raw_data=raw_data or {},
                research_source=research_source,
                researched_at=researched_at,
            )
            self._session.add(research)
            return research

        existing.status = status
        if company_overview is not None:
            existing.company_overview = company_overview
        if pain_points is not None:
            existing.pain_points = pain_points
        if tech_stack is not None:
            existing.tech_stack = tech_stack
        if recent_news is not None:
            existing.recent_news = recent_news
        if linkedin_summary is not None:
            existing.linkedin_summary = linkedin_summary
        if icp_match_score is not None:
            existing.icp_match_score = icp_match_score
        if raw_data is not None:
            existing.raw_data = raw_data
        if research_source is not None:
            existing.research_source = research_source
        if researched_at is not None:
            existing.researched_at = researched_at
        return existing
