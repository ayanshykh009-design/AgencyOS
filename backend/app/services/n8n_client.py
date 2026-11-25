"""n8n integration client — HTTP adapter for triggering n8n workflows.

Security contract: the dispatch authority is always ``N8N_BASE_URL``. Workflow
configuration may only contribute a relative ``/webhook/...`` path. Signed
outbound dispatches use ``N8N_WEBHOOK_SECRET`` over the canonical JSON request
body with the scheme ``hex(HMAC_SHA256(secret, timestamp + "." + nonce + "." + body))``.
Secrets, hostnames and raw response bodies are never logged or surfaced.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import secrets
import time
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.core.config import settings

logger = logging.getLogger("agencyos.automation.n8n")

_DEFAULT_TIMEOUT = 30.0
# Upstream response bodies are never retained — not even truncated — because
# field-name denylists cannot reliably identify every credential shape.
_REDACTED_BODY = "<redacted provider response>"
_MAX_ATTEMPTS = 3  # 2 retries after the initial attempt.
_RETRY_BACKOFF_SECONDS = 0.1
_MAX_METADATA_HEADER_CHARS = 512
_METADATA_HEADERS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("organization_id", "org_id"), "X-AgencyOS-Org-Id"),
    (("actor_id", "user_id"), "X-AgencyOS-Actor-Id"),
    (("workflow_id",), "X-AgencyOS-Workflow-Id"),
    (("execution_id",), "X-AgencyOS-Execution-Id"),
    (("idempotency_key",), "X-AgencyOS-Idempotency-Key"),
)


class N8nHttpError(Exception):
    """Raised for non-2xx responses from n8n without retaining response bodies.

    Only the status code and a fixed redaction marker are kept. The stored
    ``url`` is a relative path only — never a hostname or a signed detail.
    """

    def __init__(self, status_code: int, body: str, url: str) -> None:
        super().__init__(f"n8n request failed with status {status_code}")
        self.status_code = status_code
        self.body = _REDACTED_BODY
        self.url = _sanitize_path(url)

    @property
    def diagnostics(self) -> dict[str, Any]:
        """Structured, safe error metadata for execution error payloads."""
        return {
            "provider": "n8n",
            "status_code": self.status_code,
            "body": self.body,
        }


def _sanitize_path(url: str) -> str:
    """Keep only a relative path; never retain base URLs or credentials."""
    path = urlsplit(url or "").path
    return path if path.startswith("/webhook/") else "<redacted>"


def _validate_webhook_path(webhook_path: str) -> str:
    """Reject any workflow-supplied path that could redirect the request.

    Allowed: a relative path beginning with ``/webhook/`` containing only
    ordinary path characters. Rejected: schemes, network locations (including
    credentials), query/fragment, traversal, encoded traversal, backslashes,
    whitespace and control characters. Errors never echo the rejected value.
    """
    if not isinstance(webhook_path, str) or not webhook_path:
        raise ValueError("Invalid n8n webhook path")
    if any(ord(ch) < 32 or ord(ch) == 127 or ch.isspace() for ch in webhook_path):
        raise ValueError("Invalid n8n webhook path")
    if "\\" in webhook_path or ".." in webhook_path or "%2e" in webhook_path.lower():
        raise ValueError("Invalid n8n webhook path")

    parsed = urlsplit(webhook_path)
    if (
        parsed.scheme
        or parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Invalid n8n webhook path")
    if not webhook_path.startswith("/webhook/") or webhook_path == "/webhook/":
        raise ValueError("Invalid n8n webhook path")
    if parsed.path != webhook_path or "//" in webhook_path[1:]:
        raise ValueError("Invalid n8n webhook path")
    return webhook_path


def _canonical_body(payload: dict[str, Any]) -> bytes:
    """Stable JSON bytes used both for transport and for the HMAC."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _header_value(value: Any) -> str:
    text = str(value)
    if len(text) > _MAX_METADATA_HEADER_CHARS or any(ord(ch) < 32 or ord(ch) == 127 for ch in text):
        raise ValueError("Invalid n8n webhook metadata")
    return text


def _signature_headers(timestamp: str, nonce: str, body: bytes, secret: str) -> dict[str, str]:
    signed = timestamp.encode("ascii") + b"." + nonce.encode("ascii") + b"." + body
    digest = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return {"X-AgencyOS-Signature": digest}


def _is_transient_status(status_code: int) -> bool:
    return status_code == 429 or 500 <= status_code <= 599


async def _sleep_backoff(retry_number: int) -> None:
    """Bounded exponential backoff; monkeypatchable in tests."""
    await asyncio.sleep(_RETRY_BACKOFF_SECONDS * (2 ** (retry_number - 1)))


def _transport_error(path: str) -> N8nHttpError:
    return N8nHttpError(status_code=503, body="n8n transport error", url=path)


class N8nClient:
    """Async HTTP client for n8n webhook and API interactions."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = _DEFAULT_TIMEOUT,
        webhook_secret: str | None = None,
    ) -> None:
        self._base_url = (base_url or settings.N8N_BASE_URL).rstrip("/")
        self._api_key = api_key or ""
        self._timeout = timeout
        self._webhook_secret = (
            webhook_secret if webhook_secret is not None else settings.N8N_WEBHOOK_SECRET
        )

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["X-N8N-API-KEY"] = self._api_key
        return headers

    async def trigger_webhook(
        self,
        webhook_path: str,
        payload: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """POST to an n8n inbound webhook and return the response.

        ``metadata`` is optional and only enriches signed headers; existing
        two-argument callers are unchanged. Retries are limited to transient
        transport failures and 429/5xx responses.
        """
        path = _validate_webhook_path(webhook_path)
        if not self._base_url:
            raise ValueError("N8N_BASE_URL not configured")
        url = f"{self._base_url}{path}"

        body = _canonical_body(payload)

        for attempt in range(1, _MAX_ATTEMPTS + 1):
            headers = self._headers()
            timestamp = str(int(time.time()))
            nonce = secrets.token_hex(16)
            headers["X-AgencyOS-Timestamp"] = timestamp
            headers["X-AgencyOS-Nonce"] = nonce

            if metadata:
                for aliases, header in _METADATA_HEADERS:
                    for key in aliases:
                        value = metadata.get(key)
                        if value not in (None, ""):
                            headers[header] = _header_value(value)
                            break

            if self._webhook_secret:
                headers.update(_signature_headers(timestamp, nonce, body, self._webhook_secret))

            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.post(url, content=body, headers=headers)
            except (httpx.TimeoutException, httpx.ConnectError):
                if attempt < _MAX_ATTEMPTS:
                    await _sleep_backoff(attempt)
                    continue
                raise _transport_error(path) from None

            if _is_transient_status(response.status_code) and attempt < _MAX_ATTEMPTS:
                await _sleep_backoff(attempt)
                continue
            if response.status_code >= 400:
                raise N8nHttpError(
                    status_code=response.status_code,
                    body=response.text,
                    url=path,
                )
            return response.json() if response.content else {}

        # Unreachable: the final attempt either succeeds or raises above.
        raise _transport_error(path)

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
