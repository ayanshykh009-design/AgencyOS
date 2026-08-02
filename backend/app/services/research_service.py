"""Research Service: run AI enrichment for a lead and persist results.

Uses the LLMService with the 'signal-extraction' prompt to extract structured
signals from web search snippets, then stores them in lead_research.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.service import LLMService
from app.models.activity_log import ActivityLog
from app.models.enums import ActivityEventType
from app.models.lead import Lead
from app.models.lead_research import LeadResearch
from app.repositories.lead import LeadRepository
from app.repositories.lead_research import LeadResearchRepository
from app.services.base import utcnow


class ResearchService:
    """Owns the research workflow and transaction boundary."""

    def __init__(
        self,
        session: AsyncSession,
        llm_service: LLMService | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._session = session
        self._leads = LeadRepository(session)
        self._research_repo = LeadResearchRepository(session)
        self._http_client = http_client
        self._llm = llm_service or LLMService.for_provider(
            provider="openai",
            organization_id=None,
            session=session,
            feature="research",
        )

    async def run(
        self,
        *,
        lead_id: uuid.UUID,
        organization_id: uuid.UUID,
        force_refresh: bool = False,
    ) -> LeadResearch:
        """Run or re-run research for a lead. Returns the completed research row."""
        lead = await self._leads.get_or_404(organization_id, lead_id)

        # Check for existing completed research
        existing = await self._research_repo.get(organization_id, lead_id)
        if existing and existing.status == "completed" and not force_refresh:
            return existing

        # Mark as in_progress
        research = await self._research_repo.upsert(
            organization_id,
            lead_id,
            status="in_progress",
            researched_at=utcnow(),
        )

        try:
            # 1) Search web for recent signals about the lead
            from app.tools.registry import ToolContext
            from app.tools.web_search_tool import WebSearchTool

            ctx = ToolContext(http_client=self._http_client)
            web_search = WebSearchTool.instantiate(ctx)

            # Build search queries
            queries = self._build_search_queries(lead)
            all_snippets: list[dict[str, str]] = []
            for q in queries:
                result = await web_search.run({"query": q, "count": 3})
                if result.ok and isinstance(result.content, list):
                    all_snippets.extend(result.content)

            # 2) Extract structured signals using the signal-extraction prompt
            variables = {
                "prospect": {
                    "firstName": lead.first_name,
                    "lastName": lead.last_name,
                    "company": lead.company,
                    "role": lead.position,
                },
                "rawResearch": self._snippets_to_text(all_snippets),
            }

            rendered = self._llm.render_prompt("signal-extraction", "1.0.0", variables)

            from app.llm.models import LLMMessage, MessageRole

            chat_result = await self._llm.chat(
                [
                    LLMMessage(role=MessageRole.SYSTEM, content=rendered),
                    LLMMessage(role=MessageRole.USER, content="Extract signals."),
                ],
                temperature=0.1,
            )

            # Parse JSON output
            signals_data = self._parse_signals_json(chat_result.text)

            # 3) Store research
            research = await self._research_repo.upsert(
                organization_id,
                lead_id,
                status="completed",
                company_overview=signals_data.get("company_overview"),
                pain_points=signals_data.get("pain_points", []),
                tech_stack=signals_data.get("tech_stack", []),
                recent_news=signals_data.get("recent_news", []),
                linkedin_summary=signals_data.get("linkedin_summary"),
                icp_match_score=signals_data.get("icp_match_score"),
                raw_data={"snippets": all_snippets, "signals": signals_data},
                research_source="ai_enrichment",
                researched_at=utcnow(),
            )

            # Log activity
            self._session.add(
                ActivityLog(
                    organization_id=organization_id,
                    lead_id=lead_id,
                    event_type=ActivityEventType.RESEARCH_COMPLETED,
                    description=f"AI research completed for {lead.first_name} {lead.last_name}",
                    metadata_={"lead_id": str(lead_id)},
                    occurred_at=utcnow(),
                )
            )

            await self._session.commit()
            return research

        except Exception as exc:
            # Mark failed
            await self._research_repo.upsert(
                organization_id,
                lead_id,
                status="failed",
                raw_data={"error": str(exc)},
            )
            await self._session.commit()
            raise

    async def get(self, *, lead_id: uuid.UUID, organization_id: uuid.UUID) -> LeadResearch | None:
        return await self._research_repo.get(organization_id, lead_id)

    async def get_or_404(self, *, lead_id: uuid.UUID, organization_id: uuid.UUID) -> LeadResearch:
        return await self._research_repo.get_or_404(organization_id, lead_id)

    async def delete(self, *, lead_id: uuid.UUID, organization_id: uuid.UUID) -> bool:
        """Delete the research row. Returns True if a row was removed."""
        research = await self._research_repo.get(organization_id, lead_id)
        if research is None:
            return False
        await self._session.delete(research)
        await self._session.commit()
        return True

    def _build_search_queries(self, lead: Lead) -> list[str]:
        queries = []
        if lead.company:
            queries.append(f"{lead.company} company news funding 2024")
            queries.append(f"{lead.company} technology stack engineering")
        if lead.position:
            queries.append(f"{lead.position} challenges pain points {lead.company or ''}")
        if lead.first_name and lead.last_name and lead.company:
            queries.append(f"{lead.first_name} {lead.last_name} {lead.company} LinkedIn")
        # Deduplicate and cap
        seen = set()
        unique = []
        for q in queries:
            q = q.strip()
            if q and q not in seen:
                seen.add(q)
                unique.append(q)
        return unique[:4]

    def _snippets_to_text(self, snippets: list[dict[str, str]]) -> str:
        if not snippets:
            return "No web results found."
        lines = []
        for i, s in enumerate(snippets, 1):
            title = s.get("title", "Result")
            url = s.get("url", "")
            text = s.get("snippet", "")[:300]
            lines.append(f"{i}. {title} ({url}): {text}")
        return "\n".join(lines)

    def _parse_signals_json(self, text: str) -> dict[str, Any]:
        """Extract JSON from the model's output (handles markdown code fences)."""
        text = text.strip()
        # Remove markdown fences
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Fallback: try to find JSON object in text
            import re

            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
        return {
            "company_overview": "Could not parse structured output",
            "pain_points": [],
            "tech_stack": [],
            "recent_news": [],
            "linkedin_summary": None,
            "icp_match_score": None,
        }
