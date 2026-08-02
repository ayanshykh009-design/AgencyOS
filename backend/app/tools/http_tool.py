"""Tool: http_get — fetch a URL and return its response text."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx

from app.tools.base import Tool, ToolResult

if TYPE_CHECKING:
    pass

_DESCRIPTION = (
    "GET a URL and return up to 8,000 characters of response text. "
    "Use only for read-only access to public HTTP resources."
)
_MAX_BYTES = 8000


class HttpGetTool(Tool):
    name = "http_get"
    description = _DESCRIPTION.strip()
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "Fully-qualified URL to GET."},
        },
        "required": ["url"],
    }

    def __init__(self, client: httpx.AsyncClient | None = None, *, timeout: float = 15.0) -> None:
        self._timeout = timeout
        self._client = client or httpx.AsyncClient(timeout=self._timeout, follow_redirects=True)

    @classmethod
    def instantiate(cls, context: Any) -> HttpGetTool:
        from app.tools.registry import ToolContext

        if not isinstance(context, ToolContext):
            raise ImportError("HttpGetTool requires a ToolContext")
        client = context.http_client
        return cls(client=client)

    async def run(self, input: dict[str, Any]) -> ToolResult:
        url = input.get("url") or ""
        if not url:
            return ToolResult(ok=False, error="url is required")
        try:
            response = await self._client.get(url)
        except httpx.HTTPError as exc:
            return ToolResult(ok=False, error=str(exc))
        text = response.text[:_MAX_BYTES]
        return ToolResult(ok=True, content={"status": response.status_code, "text": text})
