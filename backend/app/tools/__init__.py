"""AI Tool Registry package.

Public API:
- Tool / ToolResult / ToolCall / ToolInput / ToolError (base)
- ToolContext / ToolRegistry / default_registry / get_tool_or_404 /
  TOOL_MANIFEST / export_manifest (registry)
- Tool classes: LeadSearchTool, LeadResearchTool, HttpGetTool, WebSearchTool,
  EmailDraftTool, N8nDispatchTool
"""

from app.tools.base import (
    Tool,
    ToolCall,
    ToolError,
    ToolInput,
    ToolResult,
)
from app.tools.email_draft_tool import EmailDraftTool
from app.tools.http_tool import HttpGetTool
from app.tools.lead_research_tool import LeadResearchTool
from app.tools.lead_search_tool import LeadSearchTool
from app.tools.n8n_tool import N8nDispatchTool
from app.tools.registry import (
    TOOL_MANIFEST,
    ToolContext,
    ToolRegistry,
    default_registry,
    export_manifest,
    get_tool_or_404,
)
from app.tools.web_search_tool import WebSearchTool

__all__ = [
    # Base types
    "Tool",
    "ToolCall",
    "ToolError",
    "ToolInput",
    "ToolResult",
    # Registry
    "ToolContext",
    "ToolRegistry",
    "default_registry",
    "export_manifest",
    "get_tool_or_404",
    "TOOL_MANIFEST",
    # Concrete tools
    "LeadSearchTool",
    "LeadResearchTool",
    "HttpGetTool",
    "WebSearchTool",
    "EmailDraftTool",
    "N8nDispatchTool",
]
