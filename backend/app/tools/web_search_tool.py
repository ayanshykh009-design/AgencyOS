"""Tool: web_search — search the web and return snippets."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx

from app.tools.base import Tool, ToolResult

if TYPE_CHECKING:
    pass

_DESCRIPTION = (
    "Search the web for recent, verifiable information about a query. "
    "Returns a list of snippets with title, URL, and text."
)
_MAX_RESULTS = 10


class WebSearchTool(Tool):
    name = "web_search"
    description = _DESCRIPTION.strip()
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query."},
            "count": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5},
        },
        "required": ["query"],
    }

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=10.0, follow_redirects=True)

    @classmethod
    def instantiate(cls, context: Any) -> WebSearchTool:
        from app.tools.registry import ToolContext

        if not isinstance(context, ToolContext):
            raise ImportError("WebSearchTool requires a ToolContext")
        client = context.http_client
        return cls(client=client)

    async def run(self, input: dict[str, Any]) -> ToolResult:
        query = input.get("query") or ""
        count = min(int(input.get("count") or 5), _MAX_RESULTS)
        if not query:
            return ToolResult(ok=False, error="query is required")

        # Use DuckDuckGo HTML endpoint (no API key required).
        url = "https://html.duckduckgo.com/html/"
        params = {"q": query}
        headers = {"User-Agent": "Mozilla/5.0 (compatible; AgencyOS/1.0)"}

        try:
            response = await self._client.post(url, data=params, headers=headers)
        except httpx.HTTPError as exc:
            return ToolResult(ok=False, error=str(exc))

        # Parse results from HTML (lightweight, no deps).
        from html.parser import HTMLParser

        class _ResultParser(HTMLParser):
            def __init__(self) -> None:
                super().__init__()
                self._in_result = False
                self._in_title = False
                self._in_snippet = False
                self._href: str | None = ""
                self._title = ""
                self._snippet = ""
                self.results: list[dict[str, str]] = []

            def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
                attrs_dict = dict(attrs)
                if tag == "a" and attrs_dict.get("class") == "result__snippet":
                    self._in_snippet = True
                if tag == "a" and attrs_dict.get("class") == "result__url":
                    self._in_title = True
                    self._href = attrs_dict.get("href", "")
                if tag == "div" and attrs_dict.get("class") == "result":
                    self._in_result = True

            def handle_endtag(self, tag: str) -> None:
                if tag == "a":
                    self._in_title = False
                    self._in_snippet = False
                if tag == "div" and self._in_result:
                    if self._title or self._snippet:
                        self.results.append(
                            {
                                "title": self._title.strip(),
                                "url": (self._href or "").strip(),
                                "snippet": self._snippet.strip(),
                            }
                        )
                    self._in_result = False
                    self._title = ""
                    self._snippet = ""
                    self._href = ""

            def handle_data(self, data: str) -> None:
                if self._in_title:
                    self._title += data
                if self._in_snippet:
                    self._snippet += data

        parser = _ResultParser()
        parser.feed(response.text)
        return ToolResult(ok=True, content=parser.results[:count])
