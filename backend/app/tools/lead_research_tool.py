"""Tool: lead_research — read (or kick off) AI research for a lead."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from app.repositories.lead import LeadRepository
from app.repositories.lead_research import LeadResearchRepository
from app.tools.base import Tool, ToolResult

if TYPE_CHECKING:
    pass

_DESCRIPTION = (
    "Read or trigger AI research for a lead: company overview, pain points, "
    "tech stack, recent news, and LinkedIn summary. Returns the research JSON."
)


class LeadResearchTool(Tool):
    """Exposes lead research to the brain."""

    name = "lead_research"
    description = _DESCRIPTION.strip()
    parameters = {
        "type": "object",
        "properties": {
            "lead_id": {"type": "string", "description": "UUID of the lead to research."},
        },
        "required": ["lead_id"],
    }

    def __init__(self, session: Any, organization_id: Any) -> None:
        self._session = session
        self._organization_id = organization_id

    @classmethod
    def instantiate(cls, context: Any) -> LeadResearchTool:
        from app.tools.registry import ToolContext

        if not isinstance(context, ToolContext):
            raise ImportError("LeadResearchTool requires a ToolContext with a session")
        if context.session is None:
            raise ImportError("LeadResearchTool requires a database session")
        return cls(context.session, context.organization_id)

    async def run(self, input: dict[str, Any]) -> ToolResult:
        raw_id = input.get("lead_id") or ""
        try:
            lead_id = uuid.UUID(str(raw_id))
        except (ValueError, TypeError):
            return ToolResult(ok=False, error=f"invalid lead_id: {raw_id!r}")

        leads_repo = LeadRepository(self._session)
        lead = await leads_repo.get(self._organization_id, lead_id)
        if lead is None:
            return ToolResult(ok=False, error="lead not found")

        research_repo = LeadResearchRepository(self._session)
        research = await research_repo.get(self._organization_id, lead_id)
        if research is None or research.status != "completed":
            # Trigger enrichment via the research service (idempotent).
            try:
                from app.services.research_service import (
                    ResearchService,  # type: ignore[import-not-found]
                )
            except ImportError:
                return ToolResult(
                    ok=False,
                    error="research service not available; run the research endpoint first",
                )

            research = await ResearchService(self._session).run(
                lead_id=lead.id, organization_id=self._organization_id
            )

        payload = {
            "lead_id": str(research.lead_id) if research else str(lead_id),
            "status": research.status if research else "failed",
            "company_overview": research.company_overview if research else None,
            "pain_points": research.pain_points if research else [],
            "tech_stack": research.tech_stack if research else [],
            "recent_news": research.recent_news if research else [],
            "linkedin_summary": research.linkedin_summary if research else None,
            "icp_match_score": research.icp_match_score if research else None,
        }
        return ToolResult(ok=True, content=payload)
