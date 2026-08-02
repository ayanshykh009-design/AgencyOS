"""Tool: lead_search — full-text search across leads in the current org."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.repositories.lead import LeadRepository
from app.tools.base import Tool, ToolResult

if TYPE_CHECKING:
    pass

_DESCRIPTION = (
    "Search leads in the current organization by name, company, email, or role. "
    "Returns a compact list of matching leads (id, name, company, role, email, score)."
)


class LeadSearchTool(Tool):
    """Thin wrapper around :class:`LeadRepository` for the AI brain."""

    name = "lead_search"
    description = _DESCRIPTION.strip()
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Free-text search term."},
            "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
        },
        "required": ["query"],
    }

    def __init__(self, session: Any, organization_id: Any) -> None:
        self._session = session
        self._organization_id = organization_id

    @classmethod
    def instantiate(cls, context: Any) -> LeadSearchTool:
        from app.tools.registry import ToolContext

        if not isinstance(context, ToolContext):
            raise ImportError("LeadSearchTool requires a ToolContext with a session")
        if context.session is None:
            raise ImportError("LeadSearchTool requires a database session")
        return cls(context.session, context.organization_id)

    async def run(self, input: dict[str, Any]) -> ToolResult:
        query = input.get("query") or ""
        limit = int(input.get("limit") or 20)
        leads_repo = LeadRepository(self._session)
        leads = await leads_repo.search(
            self._organization_id,
            query=query or None,
            limit=min(limit, 100),
        )
        results = [
            {
                "id": str(lead.id),
                "first_name": lead.first_name,
                "last_name": lead.last_name,
                "company": lead.company,
                "position": lead.position,
                "email": lead.email,
                "score": lead.score,
            }
            for lead in leads
        ]
        return ToolResult(ok=True, content=results)
