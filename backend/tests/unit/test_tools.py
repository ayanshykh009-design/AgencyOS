"""Unit tests for the AI Tool Registry: registry semantics and individual tools.

DB-bound tools (``lead_search``, ``lead_research``, ``draft_outreach``) are
exercised with stubbed repositories/sessions; HTTP tools use ``httpx`` mock
transports so nothing touches the network.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import socket
import uuid
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from app.core.config import settings
from app.tools.base import ToolResult
from app.tools.http_tool import HttpGetTool
from app.tools.lead_research_tool import LeadResearchTool
from app.tools.lead_search_tool import LeadSearchTool
from app.tools.n8n_tool import N8nDispatchTool
from app.tools.registry import TOOL_MANIFEST, ToolRegistry, default_registry
from app.tools.web_search_tool import WebSearchTool

ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
LEAD_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")


def _transport(handler: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


_PUBLIC_IP = "93.184.216.34"


async def _stub_dns(monkeypatch: pytest.MonkeyPatch, *, ip: str = _PUBLIC_IP) -> None:
    """Patch the running loop's getaddrinfo so the http tool skips real DNS."""

    loop = asyncio.get_running_loop()

    async def fake_getaddrinfo(host: str, port: int, *args: Any, **kwargs: Any) -> list[Any]:
        try:
            literal = str(ipaddress.ip_address(host))
        except ValueError:
            literal = ""
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (literal or ip, port))]

    monkeypatch.setattr(loop, "getaddrinfo", fake_getaddrinfo)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_manifest_lists_all_builtin_tools() -> None:
    names = {entry["name"] for entry in TOOL_MANIFEST}
    assert names == {
        "lead_search",
        "lead_research",
        "http_get",
        "web_search",
        "draft_outreach",
        "n8n_dispatch",
        "growth_analysis",
        "intelligence_signals",
        "summarize_context",
        "get_recent_activity",
        "create_task",
        "propose_founder_action",
    }


def test_registry_register_get_iter() -> None:
    registry = ToolRegistry()
    tool = HttpGetTool()
    registry.register(tool)
    assert registry.get("http_get") is tool
    assert registry.get("missing") is None
    assert list(registry.iter()) == [tool]
    assert registry.get_all() == [tool]


def test_registry_manifests_returns_static_entries() -> None:
    registry = ToolRegistry()
    registry.register(HttpGetTool())
    manifests = registry.manifests()
    assert [m["name"] for m in manifests] == ["http_get"]


def test_default_registry_without_context_skips_db_tools() -> None:
    # No session/org/llm -> DB-bound tools raise ImportError in instantiate and
    # are skipped; network-only tools are registered.
    registry = default_registry()
    names = {t.name for t in registry.iter()}
    assert {"http_get", "web_search", "n8n_dispatch"} <= names
    assert not ({"lead_search", "lead_research", "draft_outreach"} & names)


def test_export_manifest_is_portable() -> None:
    from app.tools.registry import export_manifest

    manifest = export_manifest()
    assert {entry["name"] for entry in manifest} == {e["name"] for e in TOOL_MANIFEST}
    for entry in manifest:
        assert {"name", "description", "parameters"} <= set(entry)


# ---------------------------------------------------------------------------
# http_get
# ---------------------------------------------------------------------------


async def test_http_get_returns_body(monkeypatch: pytest.MonkeyPatch) -> None:
    await _stub_dns(monkeypatch)
    client = _transport(lambda request: httpx.Response(200, text="<html>Hello</html>"))
    tool = HttpGetTool(client=client)
    result = await tool.run({"url": "https://example.com"})
    assert result.ok is True
    assert result.content["status"] == 200
    assert "<html>" in result.content["text"]


async def test_http_get_requires_url() -> None:
    tool = HttpGetTool(client=_transport(lambda r: httpx.Response(200)))
    result = await tool.run({})
    assert result.ok is False
    assert "url is required" in (result.error or "")


async def test_http_get_handles_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    await _stub_dns(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    tool = HttpGetTool(client=_transport(handler))
    result = await tool.run({"url": "https://example.com"})
    assert result.ok is False


# ---------------------------------------------------------------------------
# http_get SSRF hardening
# ---------------------------------------------------------------------------


async def test_http_get_rejects_private_ip_literal() -> None:
    tool = HttpGetTool(client=_transport(lambda r: httpx.Response(200)))
    for url in (
        "http://127.0.0.1/",
        "http://10.0.0.5/admin",
        "http://192.168.1.10/",
        "http://169.254.169.254/latest/meta-data/",
        "http://172.16.0.1/",
    ):
        result = await tool.run({"url": url})
        assert result.ok is False, url
        assert "non-public address" in (result.error or "")


async def test_http_get_rejects_ipv6_loopback() -> None:
    tool = HttpGetTool(client=_transport(lambda r: httpx.Response(200)))
    result = await tool.run({"url": "http://[::1]/"})
    assert result.ok is False
    assert "non-public address" in (result.error or "")


async def test_http_get_rejects_non_http_scheme() -> None:
    tool = HttpGetTool(client=_transport(lambda r: httpx.Response(200)))
    for url in ("file:///etc/passwd", "ftp://example.com/file", "gopher://example.com/x"):
        result = await tool.run({"url": url})
        assert result.ok is False, url
        assert "only http/https URLs are allowed" in (result.error or "")


async def test_http_get_rejects_embedded_credentials() -> None:
    tool = HttpGetTool(client=_transport(lambda r: httpx.Response(200)))
    result = await tool.run({"url": "https://user:pass@example.com/"})
    assert result.ok is False
    assert "embedded credentials" in (result.error or "")


async def test_http_get_rejects_non_standard_port() -> None:
    tool = HttpGetTool(client=_transport(lambda r: httpx.Response(200)))
    for url in ("https://example.com:8443/", "http://example.com:8080/"):
        result = await tool.run({"url": url})
        assert result.ok is False, url
        assert "port" in (result.error or "")


async def test_http_get_rejects_dns_to_private_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    await _stub_dns(monkeypatch, ip="10.0.0.5")
    tool = HttpGetTool(client=_transport(lambda r: httpx.Response(200)))
    result = await tool.run({"url": "https://internal.corp.local/"})
    assert result.ok is False
    assert "non-public address" in (result.error or "")


async def test_http_get_follows_public_redirect(monkeypatch: pytest.MonkeyPatch) -> None:
    await _stub_dns(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "https://example.com/target"})
        return httpx.Response(200, text="landed")

    tool = HttpGetTool(client=_transport(handler))
    result = await tool.run({"url": "https://example.com/start"})
    assert result.ok is True
    assert result.content["text"] == "landed"


async def test_http_get_rejects_redirect_to_private_url(monkeypatch: pytest.MonkeyPatch) -> None:
    await _stub_dns(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "http://192.168.1.1/admin"})
        return httpx.Response(200, text="landed")

    tool = HttpGetTool(client=_transport(handler))
    result = await tool.run({"url": "https://example.com/start"})
    assert result.ok is False
    assert "non-public address" in (result.error or "")


async def test_http_get_rejects_redirect_to_non_http_scheme(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _stub_dns(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "file:///etc/passwd"})
        return httpx.Response(200, text="landed")

    tool = HttpGetTool(client=_transport(handler))
    result = await tool.run({"url": "https://example.com/start"})
    assert result.ok is False


async def test_http_get_stops_after_too_many_redirects(monkeypatch: pytest.MonkeyPatch) -> None:
    await _stub_dns(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "/loop"})

    tool = HttpGetTool(client=_transport(handler))
    result = await tool.run({"url": "https://example.com/start"})
    assert result.ok is False
    assert "too many redirects" in (result.error or "")


# ---------------------------------------------------------------------------
# web_search
# ---------------------------------------------------------------------------


def _ddg_html() -> str:
    return (
        '<div class="result"><a class="result__url" href="https://e.com/a">Example Corp</a>'
        '<a class="result__snippet">Funding news snippet</a></div>'
    )


async def test_web_search_parses_results() -> None:
    client = _transport(lambda request: httpx.Response(200, text=_ddg_html()))
    tool = WebSearchTool(client=client)
    result = await tool.run({"query": "example corp", "count": 5})
    assert result.ok is True
    assert result.content == [
        {"title": "Example Corp", "url": "https://e.com/a", "snippet": "Funding news snippet"}
    ]


async def test_web_search_requires_query() -> None:
    tool = WebSearchTool(client=_transport(lambda r: httpx.Response(200)))
    result = await tool.run({})
    assert result.ok is False
    assert "query is required" in (result.error or "")


# ---------------------------------------------------------------------------
# n8n_dispatch
# ---------------------------------------------------------------------------


async def test_n8n_dispatch_posts_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content or b"{}")
        return httpx.Response(200, json={"success": True})

    monkeypatch.setattr(settings, "N8N_BASE_URL", "https://n8n.example.com")
    tool = N8nDispatchTool(client=_transport(handler))
    result = await tool.run({"workflow": "outreach-dispatch", "payload": {"lead_id": str(LEAD_ID)}})
    assert result.ok is True
    assert captured["url"].endswith("/webhook/outreach-dispatch")
    assert captured["body"]["lead_id"] == str(LEAD_ID)


async def test_n8n_dispatch_requires_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "N8N_BASE_URL", "")
    tool = N8nDispatchTool(client=_transport(lambda r: httpx.Response(200)))
    result = await tool.run({"workflow": "outreach-dispatch", "payload": {}})
    assert result.ok is False
    assert "N8N_BASE_URL" in (result.error or "")


async def test_n8n_dispatch_rejects_unknown_workflow(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "N8N_BASE_URL", "https://n8n.example.com")
    tool = N8nDispatchTool(client=_transport(lambda r: httpx.Response(200)))
    result = await tool.run({"workflow": "no-such", "payload": {}})
    assert result.ok is False
    assert "unknown workflow" in (result.error or "")


# ---------------------------------------------------------------------------
# lead_search
# ---------------------------------------------------------------------------


class _FakeLeadRepo:
    """Stub for LeadRepository.search used by LeadSearchTool."""

    def __init__(self, session: Any) -> None:
        self.session = session

    async def search(self, organization_id: Any, *, query: str | None, limit: int) -> list:
        return [
            SimpleNamespace(
                id=LEAD_ID,
                first_name="Ada",
                last_name="Lovelace",
                company="Analytical",
                position="Engineer",
                email="ada@example.com",
                score=80,
            )
        ]


async def test_lead_search_returns_compact_results(monkeypatch: pytest.MonkeyPatch) -> None:
    session = SimpleNamespace()
    tool = LeadSearchTool(session, ORG_ID)
    monkeypatch.setattr("app.tools.lead_search_tool.LeadRepository", _FakeLeadRepo)

    result = await tool.run({"query": "ada", "limit": 5})
    assert result.ok is True
    assert result.content == [
        {
            "id": str(LEAD_ID),
            "first_name": "Ada",
            "last_name": "Lovelace",
            "company": "Analytical",
            "position": "Engineer",
            "email": "ada@example.com",
            "score": 80,
        }
    ]


# ---------------------------------------------------------------------------
# lead_research
# ---------------------------------------------------------------------------


async def test_lead_research_invalid_id(monkeypatch: pytest.MonkeyPatch) -> None:
    session = SimpleNamespace()
    tool = LeadResearchTool(session, ORG_ID)
    result = await tool.run({"lead_id": "not-a-uuid"})
    assert result.ok is False
    assert "invalid lead_id" in (result.error or "")


# ---------------------------------------------------------------------------
# ToolResult
# ---------------------------------------------------------------------------


def test_tool_result_is_error_flag_derives_from_ok() -> None:
    assert ToolResult(ok=True).is_error is False
    failed = ToolResult(ok=False, error="nope")
    assert failed.is_error is True
    assert failed.text == "nope"


def test_tool_result_text_serializes_content() -> None:
    assert ToolResult(ok=True, content="plain").text == "plain"
    assert ToolResult(ok=True, content={"k": "v"}).text == json.dumps({"k": "v"})
