"""Tool: n8n_dispatch — hand off a ready-to-send outreach draft to n8n automation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx

from app.tools.base import Tool, ToolResult

if TYPE_CHECKING:
    pass

_DESCRIPTION = (
    "Dispatch an outreach draft to the n8n automation platform via its inbound webhook. "
    "The n8n workflow handles actual sending (SMTP/LinkedIn/WhatsApp)."
)

_WORKFLOW_PATHS = {
    "outreach-dispatch": "/webhook/outreach-dispatch",
}


class N8nDispatchTool(Tool):
    name = "n8n_dispatch"
    description = _DESCRIPTION.strip()
    parameters = {
        "type": "object",
        "properties": {
            "workflow": {
                "type": "string",
                "description": "n8n workflow key (e.g. outreach-dispatch).",
            },
            "payload": {"type": "object", "description": "Arbitrary JSON the workflow accepts."},
        },
        "required": ["workflow", "payload"],
    }

    def __init__(self, client: httpx.AsyncClient | None = None, base_url: str = "") -> None:
        self._client = client or httpx.AsyncClient(timeout=30.0)
        self._base_url = base_url.rstrip("/")

    @classmethod
    def instantiate(cls, context: Any) -> N8nDispatchTool:
        from app.tools.registry import ToolContext

        if not isinstance(context, ToolContext):
            raise ImportError("N8nDispatchTool requires a ToolContext")
        client = context.http_client
        return cls(client=client, base_url="")

    async def run(self, input: dict[str, Any]) -> ToolResult:
        workflow = input.get("workflow") or ""
        payload = input.get("payload") or {}

        from app.core.config import settings

        base = settings.N8N_BASE_URL or self._base_url
        if not base:
            return ToolResult(ok=False, error="N8N_BASE_URL not configured")

        path = _WORKFLOW_PATHS.get(workflow)
        if path is None:
            return ToolResult(ok=False, error=f"unknown workflow: {workflow}")

        url = f"{base}{path}"
        try:
            response = await self._client.post(url, json=payload)
            response.raise_for_status()
            return ToolResult(
                ok=True, content={"status": response.status_code, "data": response.json()}
            )
        except httpx.HTTPError as exc:
            return ToolResult(ok=False, error=f"n8n dispatch failed: {exc}")
