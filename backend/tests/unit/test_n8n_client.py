"""Unit tests: n8n integration client (webhook/status/health)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx

from app.services.n8n_client import N8nClient, get_n8n_client

_BASE = "https://n8n.example.com"


async def test_trigger_webhook_async(monkeypatch) -> None:
    captured: dict = {}

    async def _fake_post(client: httpx.AsyncClient, url: str, **kwargs: object) -> MagicMock:
        captured["url"] = url
        captured["json"] = kwargs["json"]
        captured["headers"] = kwargs["headers"]
        response = MagicMock()
        response.content = b'{"ok": true}'
        response.json.return_value = {"ok": True}
        return response

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)

    client = N8nClient(base_url=_BASE, api_key="k")
    result = await client.trigger_webhook("/webhook/x", {"a": 1})

    assert result == {"ok": True}
    assert captured["url"] == f"{_BASE}/webhook/x"
    assert captured["json"] == {"a": 1}
    assert captured["headers"]["X-N8N-API-KEY"] == "k"


async def test_health_check_returns_true_on_200(monkeypatch) -> None:
    response = MagicMock()
    response.status_code = 200
    monkeypatch.setattr(httpx.AsyncClient, "get", AsyncMock(return_value=response))

    client = N8nClient(base_url=_BASE)
    assert await client.health_check() is True


async def test_health_check_returns_false_on_error(monkeypatch) -> None:
    async def _boom(*args: object, **kwargs: object) -> None:
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx.AsyncClient, "get", _boom)

    client = N8nClient(base_url=_BASE)
    assert await client.health_check() is False


async def test_get_workflow_status_without_key_returns_none(monkeypatch) -> None:
    get_called = False

    async def _get(*args: object, **kwargs: object) -> MagicMock:
        nonlocal get_called
        get_called = True
        raise AssertionError("should not call the API without a key")

    monkeypatch.setattr(httpx.AsyncClient, "get", _get)

    client = N8nClient(base_url=_BASE, api_key="")
    assert await client.get_workflow_status("w1") is None
    assert get_called is False


async def test_trigger_webhook_requires_base_url() -> None:
    import pytest

    client = N8nClient(base_url="")
    with pytest.raises(ValueError, match="N8N_BASE_URL"):
        await client.trigger_webhook("/webhook/x", {"a": 1})


def test_get_n8n_client_factory(monkeypatch) -> None:
    from app.services import n8n_client

    monkeypatch.setattr(n8n_client.settings, "N8N_BASE_URL", _BASE)
    client = get_n8n_client()
    assert isinstance(client, N8nClient)
