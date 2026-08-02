"""Tool: draft_outreach — generate personalized cold email/LinkedIn message from research."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from app.repositories.lead import LeadRepository
from app.repositories.lead_research import LeadResearchRepository
from app.tools.base import Tool, ToolResult

if TYPE_CHECKING:
    from app.llm.service import LLMService

_DESCRIPTION = (
    "Draft a personalized cold email or LinkedIn connection request for a lead. "
    "Uses the lead's research signals and a versioned prompt to produce a ready-to-send message."
)

_PROMPT_MAP = {
    "email": ("ice-breaker", "1.0.0"),
    "linkedin": ("connection-request", "1.0.0"),
}


class EmailDraftTool(Tool):
    name = "draft_outreach"
    description = _DESCRIPTION.strip()
    parameters = {
        "type": "object",
        "properties": {
            "lead_id": {"type": "string", "description": "UUID of the lead."},
            "channel": {
                "type": "string",
                "enum": ["email", "linkedin"],
                "default": "email",
                "description": "Outreach channel to draft for.",
            },
        },
        "required": ["lead_id"],
    }

    def __init__(self, llm_service: LLMService, session: Any, organization_id: Any) -> None:
        self._llm = llm_service
        self._session = session
        self._organization_id = organization_id

    @classmethod
    def instantiate(cls, context: Any) -> EmailDraftTool:
        from app.tools.registry import ToolContext

        if not isinstance(context, ToolContext):
            raise ImportError("EmailDraftTool requires a ToolContext with llm_service and session")
        if context.llm_service is None:
            raise ImportError("EmailDraftTool requires an LLMService")
        if context.session is None:
            raise ImportError("EmailDraftTool requires a database session")
        return cls(context.llm_service, context.session, context.organization_id)

    async def run(self, input: dict[str, Any]) -> ToolResult:
        raw_id = input.get("lead_id") or ""
        channel = (input.get("channel") or "email").lower()
        if channel not in _PROMPT_MAP:
            return ToolResult(ok=False, error=f"unsupported channel: {channel}")

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

        prompt_name, prompt_version = _PROMPT_MAP[channel]
        variables = {
            "prospect": {
                "firstName": lead.first_name,
                "lastName": lead.last_name,
                "company": lead.company,
                "role": lead.position,
            },
            "signal": self._extract_signal(research),
            "senderIdentity": "AI Outreach Agent",
        }

        try:
            # Use the LLMService's built-in prompt rendering + chat.
            from app.llm.models import LLMMessage, MessageRole

            rendered = self._llm.render_prompt(prompt_name, prompt_version, variables)
            chat_result = await self._llm.chat(
                [
                    LLMMessage(role=MessageRole.SYSTEM, content=rendered),
                    LLMMessage(role=MessageRole.USER, content="Write the outreach message."),
                ]
            )
            draft = chat_result.text.strip()
        except Exception as exc:  # pragma: no cover - network failure
            return ToolResult(ok=False, error=f"draft generation failed: {exc}")

        return ToolResult(
            ok=True, content={"draft": draft, "channel": channel, "lead_id": str(lead_id)}
        )

    def _extract_signal(self, research: Any | None) -> str:
        if research is None:
            return "No research available."
        parts = []
        if research.company_overview:
            parts.append(f"Company: {research.company_overview[:300]}")
        if research.pain_points:
            parts.append(f"Pain points: {', '.join(str(p) for p in research.pain_points[:3])}")
        if research.recent_news:
            parts.append(f"Recent news: {research.recent_news[0][:300]}")
        return " | ".join(parts) if parts else "No specific signals found."
