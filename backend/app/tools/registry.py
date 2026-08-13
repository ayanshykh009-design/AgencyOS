"""Tool Registry — dynamic lookup of AI-callable tools by name.

The registry is the brain's single source of truth for available tools. It is
populated from a declarative manifest (see :data:`TOOL_MANIFEST`) so the tool
set can also be exported (e.g. to an MCP server) from one source.

At runtime the brain constructs tools *with their dependencies* (session, org
id, llm service, ...) and registers the instances here; the manifest supplies the
static metadata (name/description/parameters) and the implementation module so
that ``export_manifest()`` can describe the full tooling surface without a live
process.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Protocol

from app.tools.base import Tool, ToolCall, ToolError, ToolInput, ToolResult

__all__ = [
    "Tool",
    "ToolCall",
    "ToolError",
    "ToolInput",
    "ToolResult",
    "ToolContext",
    "ToolRegistry",
    "default_registry",
    "get_tool_or_404",
    "TOOL_MANIFEST",
    "export_manifest",
]


@dataclass
class ToolContext:
    """Runtime dependencies injected into tools at construction time."""

    session: Any = None
    organization_id: Any = None
    llm_service: Any = None
    http_client: Any = None


# Manifest: one entry per tool. Drives discovery, the MCP/JSON export, and the
# n8n dispatch table. New tools append a row. ``module`` is the implementation
# (used only for static export/introspection, not for lazy import here).
TOOL_MANIFEST: list[dict[str, Any]] = [
    {
        "name": "lead_search",
        "description": "Search leads in the current org by keyword (name/company/email/role).",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Free-text search term."},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
            },
            "required": ["query"],
        },
        "module": "app.tools.lead_search_tool:LeadSearchTool",
    },
    {
        "name": "lead_research",
        "description": (
            "Read or trigger AI research (company overview, pain points, tech stack) for a lead."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "lead_id": {"type": "string", "description": "UUID of the lead to research."},
            },
            "required": ["lead_id"],
        },
        "module": "app.tools.lead_research_tool:LeadResearchTool",
    },
    {
        "name": "http_get",
        "description": "GET a URL and return up to 8,000 characters of response text.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Fully-qualified URL to GET."},
            },
            "required": ["url"],
        },
        "module": "app.tools.http_tool:HttpGetTool",
    },
    {
        "name": "web_search",
        "description": "Search the web for recent information about a query and return snippets.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query."},
                "count": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5},
            },
            "required": ["query"],
        },
        "module": "app.tools.web_search_tool:WebSearchTool",
    },
    {
        "name": "draft_outreach",
        "description": (
            "Draft a personalized cold email/LinkedIn message for a lead using a "
            "versioned prompt and the lead's research signals."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "lead_id": {"type": "string", "description": "UUID of the lead."},
                "channel": {
                    "type": "string",
                    "enum": ["email", "linkedin"],
                    "default": "email",
                },
            },
            "required": ["lead_id"],
        },
        "module": "app.tools.email_draft_tool:EmailDraftTool",
    },
    {
        "name": "n8n_dispatch",
        "description": (
            "Hand off a ready-to-send outreach draft to the n8n automation via its inbound webhook."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "workflow": {
                    "type": "string",
                    "description": "n8n workflow key (e.g. outreach-dispatch).",
                },
                "payload": {
                    "type": "object",
                    "description": "Arbitrary JSON the workflow accepts.",
                },
            },
            "required": ["workflow", "payload"],
        },
        "module": "app.tools.n8n_tool:N8nDispatchTool",
    },
    {
        "name": "growth_analysis",
        "description": (
            "Run a deterministic growth analysis for the current organization "
            "(kpis, pipeline, funnel, conversion, revenue, activity, bottlenecks, "
            "opportunities, trends, or health) and return the structured result. "
            "Read-only."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "analysis_type": {
                    "type": "string",
                    "enum": [
                        "health",
                        "kpis",
                        "pipeline",
                        "funnel",
                        "conversion",
                        "revenue",
                        "activity",
                        "bottlenecks",
                        "opportunities",
                        "trends",
                    ],
                    "description": "Which deterministic engine to run.",
                },
                "period_start": {
                    "type": "string",
                    "format": "date-time",
                    "description": "ISO-8601 window start (defaults to 30 days ago).",
                },
                "period_end": {
                    "type": "string",
                    "format": "date-time",
                    "description": "ISO-8601 window end (defaults to now).",
                },
            },
            "required": ["analysis_type"],
        },
        "module": "app.tools.growth_tool:GrowthAnalysisTool",
    },
]


class ToolRegistry:
    """In-memory registry of instantiated tools, keyed by name."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool instance (already built with its dependencies)."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def get_all(self) -> list[Any]:
        """All registered tools."""
        return list(self._tools.values())

    def manifests(self) -> list[dict[str, Any]]:
        """Static manifest entries for the registered tool names."""
        names = {t.name for t in self._tools.values()}
        return [entry for entry in TOOL_MANIFEST if entry["name"] in names]

    def iter(self) -> Iterable[Tool]:
        return iter(self._tools.values())


def get_tool_or_404(registry: ToolRegistry, name: str) -> Tool:
    """Return the tool, raising ``ValueError`` when unknown."""
    tool = registry.get(name)
    if tool is None:
        raise ValueError(f"unknown tool: {name}")
    return tool


def export_manifest() -> list[dict[str, Any]]:
    """Return a portable, static description of the full tool surface.

    Used for MCP server capability export and n8n dispatch discovery. Unlike
    :meth:`ToolRegistry.get_all`, this does not require runtime dependencies.
    """
    return [
        {
            "name": entry["name"],
            "description": entry["description"],
            "parameters": entry["parameters"],
        }
        for entry in TOOL_MANIFEST
    ]


def default_registry(context: ToolContext | None = None) -> ToolRegistry:
    """Build a registry and instantiate all built-in tools with ``context``.

    Tools whose backend raises ``ImportError`` (optional dependencies not
    installed) are skipped so the brain can still operate with a reduced set.
    """
    from app.tools.email_draft_tool import EmailDraftTool
    from app.tools.growth_tool import GrowthAnalysisTool
    from app.tools.http_tool import HttpGetTool
    from app.tools.lead_research_tool import LeadResearchTool
    from app.tools.lead_search_tool import LeadSearchTool
    from app.tools.n8n_tool import N8nDispatchTool
    from app.tools.web_search_tool import WebSearchTool

    class _ToolBuilder(Protocol):
        @classmethod
        def instantiate(cls, context: ToolContext) -> Tool: ...

    ctx = context or ToolContext()
    registry = ToolRegistry()
    builders: list[type[_ToolBuilder]] = [
        LeadSearchTool,
        LeadResearchTool,
        HttpGetTool,
        WebSearchTool,
        EmailDraftTool,
        N8nDispatchTool,
        GrowthAnalysisTool,
    ]
    for builder in builders:
        try:
            registry.register(builder.instantiate(ctx))
        except ImportError:
            continue
    return registry
