"""n8n integration client — HTTP adapter for triggering n8n workflows."""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger("agencyos.automation.n8n")

_DEFAULT_TIMEOUT = 30.0


class N8nClient:
    """Async HTTP client for n8n webhook and API interactions."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self._base_url = (base_url or settings.N8N_BASE_URL).rstrip("/")
        self._api_key = api_key or ""
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["X-N8N-API-KEY"] = self._api_key
        return headers

    async def trigger_webhook(
        self,
        webhook_path: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """POST to an n8n inbound webhook and return the response."""
        if not self._base_url:
            raise ValueError("N8N_BASE_URL not configured")
        url = f"{self._base_url}{webhook_path}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(url, json=payload, headers=self._headers())
            response.raise_for_status()
            return response.json() if response.content else {}

    async def get_workflow_status(self, workflow_id: str) -> dict[str, Any] | None:
        """Fetch workflow status from n8n API (best-effort)."""
        if not self._api_key:
            logger.debug("n8n API key not set — skipping status check")
            return None
        url = f"{self._base_url}/api/v1/workflows/{workflow_id}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(url, headers=self._headers())
            response.raise_for_status()
            return response.json()

    async def health_check(self) -> bool:
        """Check if n8n is reachable."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"{self._base_url}/healthz",
                    headers=self._headers(),
                )
                return response.status_code == 200
        except httpx.HTTPError:
            return False


def get_n8n_client(api_key: str | None = None) -> N8nClient:
    """Factory for N8nClient using global settings."""
    return N8nClient(api_key=api_key)
