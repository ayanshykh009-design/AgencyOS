"""Research worker: background job to run AI enrichment for a lead.

Mirrors the ImportWorker pattern: runs in its own session/transaction, safe for
background execution. Called from the research endpoint via BackgroundTasks.
"""

from __future__ import annotations

import logging
import uuid

from app.core.database import async_session_factory
from app.repositories.lead_research import LeadResearchRepository

logger = logging.getLogger("agencyos")


class ResearchWorker:
    """Process a single lead research job end-to-end."""

    @classmethod
    async def process_job(
        cls,
        lead_id: uuid.UUID,
        organization_id: uuid.UUID,
        *,
        force_refresh: bool = False,
    ) -> None:
        """Run the research; safe to call from a background task."""
        try:
            await cls._run(lead_id, organization_id, force_refresh=force_refresh)
        except Exception:
            logger.exception("research job for lead %s failed", lead_id)
            await cls._mark_failed(lead_id, organization_id)

    @classmethod
    async def _run(
        cls,
        lead_id: uuid.UUID,
        organization_id: uuid.UUID,
        *,
        force_refresh: bool = False,
    ) -> None:
        async with async_session_factory() as session:
            from app.services.research_service import ResearchService

            await ResearchService(session).run(
                lead_id=lead_id,
                organization_id=organization_id,
                force_refresh=force_refresh,
            )
            logger.info("research job completed for lead %s", lead_id)

    @classmethod
    async def _mark_failed(cls, lead_id: uuid.UUID, organization_id: uuid.UUID) -> None:
        """Best-effort: flag the research failed after an unexpected error."""
        try:
            async with async_session_factory() as session:
                repo = LeadResearchRepository(session)
                await repo.upsert(
                    organization_id,
                    lead_id,
                    status="failed",
                    raw_data={"error": "worker exception"},
                )
                await session.commit()
        except Exception:
            logger.exception("could not mark research failed for lead %s", lead_id)
