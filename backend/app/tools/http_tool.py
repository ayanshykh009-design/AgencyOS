"""Tool: http_get — fetch a URL and return its response text.

Hardened against SSRF: only public http(s) URLs are allowed, the host must not
resolve to a private/loopback/link-local address, only standard ports are
accepted, and every redirect hop is re-validated before it is followed.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

from app.tools.base import Tool, ToolResult

_MAX_BYTES = 8000
_MAX_REDIRECTS = 5
_ALLOWED_PORTS = frozenset({80, 443})

# IPv4 networks that must never be fetched: private, loopback, link-local,
# CGNAT, reserved, multicast, and documentation ranges.
_BLOCKED_IPV4 = (
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("255.255.255.255/32"),
)

_BLOCKED_IPV6 = (
    ipaddress.ip_network("::/128"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("fec0::/10"),
    ipaddress.ip_network("ff00::/8"),
    ipaddress.ip_network("2001:db8::/32"),
)

_DESCRIPTION = (
    "GET a URL and return up to 8,000 characters of response text. "
    "Use only for read-only access to public HTTP resources."
)


def _is_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if ip.version == 4:
        return not any(ip in network for network in _BLOCKED_IPV4)
    if ip.ipv4_mapped is not None:
        return _is_public_ip(ip.ipv4_mapped)
    return not any(ip in network for network in _BLOCKED_IPV6)


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
        self._client = client or httpx.AsyncClient(timeout=self._timeout, follow_redirects=False)

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
            text, status = await self._fetch(url)
        except (httpx.HTTPError, ValueError) as exc:
            return ToolResult(ok=False, error=str(exc))
        return ToolResult(ok=True, content={"status": status, "text": text})

    async def _fetch(self, url: str) -> tuple[str, int]:
        client = self._client
        if getattr(client, "follow_redirects", False):
            client = httpx.AsyncClient(timeout=self._timeout, follow_redirects=False)
        current = await self._validated_url(url)
        for _ in range(_MAX_REDIRECTS + 1):
            response = await client.get(current)
            if response.status_code in (301, 302, 303, 307, 308) and response.headers.get(
                "location"
            ):
                current = await self._validated_url(
                    urljoin(current, response.headers["location"])
                )
                continue
            return response.text[:_MAX_BYTES], response.status_code
        raise ValueError(f"too many redirects ({_MAX_REDIRECTS})")

    async def _validated_url(self, url: str) -> str:
        try:
            parsed = urlsplit(url)
        except ValueError as exc:
            raise ValueError("invalid URL") from exc
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"only http/https URLs are allowed, got scheme {parsed.scheme!r}")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("URLs with embedded credentials are not allowed")
        hostname = parsed.hostname
        if not hostname:
            raise ValueError("URL is missing a hostname")
        try:
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
        except ValueError as exc:
            raise ValueError("invalid port") from exc
        if port not in _ALLOWED_PORTS:
            raise ValueError(f"port {port} is not allowed")
        loop = asyncio.get_running_loop()
        try:
            infos = await loop.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise ValueError(f"could not resolve host {hostname!r}") from exc
        seen: set[str] = set()
        for _family, _type, _proto, _canon, sockaddr in infos:
            ip = ipaddress.ip_address(sockaddr[0])
            key = str(ip)
            if key in seen:
                continue
            seen.add(key)
            if not _is_public_ip(ip):
                raise ValueError(f"host {hostname!r} resolves to a non-public address")
        return url
