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

from app.core.permissions import Permission
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
    "ToolAuthorizationError",
    "assert_can_invoke_tool",
    "required_permission_for",
    "is_side_effecting",
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
        "required_permission": Permission.LEAD_READ,
        "side_effect": False,
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
        "required_permission": Permission.LEAD_READ,
        "side_effect": False,
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
        "required_permission": Permission.AI_RUN,
        "side_effect": False,
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
        "required_permission": Permission.AI_RUN,
        "side_effect": False,
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
        "required_permission": Permission.LEAD_WRITE,
        "side_effect": False,
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
        "required_permission": Permission.LEAD_WRITE,
        "side_effect": True,
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
        "required_permission": Permission.GROWTH_READ,
        "side_effect": False,
    },
    {
        "name": "intelligence_signals",
        "description": (
            "List founder-facing intelligence signals for the current organization "
            "(prioritized business insights derived from validated data). Read-only."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["new", "acknowledged", "in_progress", "resolved", "dismissed"],
                    "description": "Filter by signal status.",
                },
                "category": {
                    "type": "string",
                    "enum": [
                        "market_shift",
                        "competitor_move",
                        "customer_signal",
                        "funding_signal",
                        "macro_trend",
                        "operational_risk",
                    ],
                    "description": "Filter by signal category.",
                },
                "source_type": {
                    "type": "string",
                    "enum": ["lead", "outreach", "growth", "web", "founder", "system"],
                    "description": "Filter by originating data source type.",
                },
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
                "offset": {"type": "integer", "minimum": 0, "default": 0},
            },
            "required": [],
        },
        "module": "app.tools.intelligence_signals_tool:IntelligenceSignalsTool",
        "required_permission": Permission.INTELLIGENCE_READ,
        "side_effect": False,
    },
    {
        "name": "summarize_context",
        "description": "Summarize the founder's business context for the assistant.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
        "module": "app.tools.founder_tools:SummarizeContextTool",
        "required_permission": Permission.FOUNDER_READ,
        "side_effect": False,
    },
    {
        "name": "get_recent_activity",
        "description": "List recent org activity for the founder assistant.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
        "module": "app.tools.founder_tools:GetRecentActivityTool",
        "required_permission": Permission.FOUNDER_READ,
        "side_effect": False,
    },
    {
        "name": "create_task",
        "description": "Create an internal task on behalf of the founder (requires approval).",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Task title."},
            },
            "required": ["title"],
        },
        "module": "app.tools.founder_tools:CreateTaskTool",
        "required_permission": Permission.FOUNDER_MANAGE,
        "side_effect": True,
    },
    {
        "name": "propose_founder_action",
        "description": "Propose a founder action that requires approval before execution.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Proposal title."},
            },
            "required": ["title"],
        },
        "module": "app.tools.founder_tools:ProposeFounderActionTool",
        "required_permission": Permission.FOUNDER_MANAGE,
        "side_effect": True,
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


class ToolAuthorizationError(Exception):
    """Raised when a tool invocation is not permitted for a caller/goal."""


# Index the manifest's authorization metadata for O(1) lookups.
_MANIFEST_BY_NAME: dict[str, dict[str, Any]] = {e["name"]: e for e in TOOL_MANIFEST}


def required_permission_for(name: str) -> Permission | None:
    """Return the permission required to invoke ``name`` (``None`` if unknown)."""
    entry = _MANIFEST_BY_NAME.get(name)
    if entry is None:
        return None
    return entry.get("required_permission")


def is_side_effecting(name: str) -> bool:
    """Return whether invoking ``name`` triggers an external side effect."""
    entry = _MANIFEST_BY_NAME.get(name)
    if entry is None:
        return True  # unknown tools are treated as unsafe until declared
    return bool(entry.get("side_effect", True))


def assert_can_invoke_tool(
    caller_permissions: frozenset[Permission] | None,
    name: str,
) -> None:
    """Enforce per-tool authorization; fail closed when denied or unknown.

    ``caller_permissions`` is the closed permission set of the acting user. When
    ``None`` (legacy/trusted callers), authorization is skipped — but every AI
    run path must pass a real permission set so unauthorized tools are rejected.
    """
    if caller_permissions is None:
        return
    required = required_permission_for(name)
    if required is None:
        raise ToolAuthorizationError(
            f"tool {name!r} is not registered and cannot be authorized"
        )
    if required not in caller_permissions:
        raise ToolAuthorizationError(
            f"caller lacks permission {required.value!r} required for tool {name!r}"
        )


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
    from app.tools.intelligence_signals_tool import IntelligenceSignalsTool
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
        IntelligenceSignalsTool,
    ]
    for builder in builders:
        try:
            registry.register(builder.instantiate(ctx))
        except ImportError:
            continue
    return registry
