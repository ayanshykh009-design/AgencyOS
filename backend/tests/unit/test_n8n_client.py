"""Unit tests: n8n integration client (path safety, signing, retries, errors)."""

from __future__ import annotations

import hashlib
import hmac
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.services import n8n_client
from app.services.n8n_client import N8nClient, N8nHttpError, get_n8n_client

_BASE = "https://n8n.example.com"
_SIGNING_SECRET = "outbound-signing-test-secret"


def _response(
    status_code: int, body: bytes = b'{"ok": true}', payload: dict | None = None
) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.content = body
    response.text = body.decode("utf-8", errors="replace")
    response.json.return_value = payload if payload is not None else {"ok": True}
    return response


async def test_trigger_webhook_async(monkeypatch) -> None:
    captured: dict = {}

    async def _fake_post(client: httpx.AsyncClient, url: str, **kwargs: object) -> MagicMock:
        captured["url"] = url
        captured["content"] = kwargs["content"]
        captured["headers"] = kwargs["headers"]
        return _response(200)

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)

    client = N8nClient(base_url=_BASE, api_key="k")
    result = await client.trigger_webhook("/webhook/x", {"a": 1})

    assert result == {"ok": True}
    assert captured["url"] == f"{_BASE}/webhook/x"
    assert captured["content"] == b'{"a":1}'
    assert captured["headers"]["X-N8N-API-KEY"] == "k"
    assert "X-AgencyOS-Timestamp" in captured["headers"]
    assert "X-AgencyOS-Nonce" in captured["headers"]


@pytest.mark.parametrize(
    "path",
    [
        "https://evil.example/webhook/x",
        "https://user:pass@evil.example/webhook/x",
        "//evil.example/webhook/x",
        "/webhook/../admin",
        "/webhook/%2e%2e/x",
        "/webhook/x?key=secret",
        "/webhook/x#fragment",
        "/webhook/x\\y",
        "/webhook/x\ninjected",
        "/webhook/",
        "webhook/x",
        "/other/x",
    ],
)
async def test_trigger_webhook_rejects_unsafe_paths(monkeypatch, path: str) -> None:
    post = AsyncMock()
    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    client = N8nClient(base_url=_BASE)
    with pytest.raises(ValueError, match="Invalid n8n webhook path"):
        await client.trigger_webhook(path, {"a": 1})
    post.assert_not_awaited()


async def test_trigger_webhook_signs_canonical_body_with_configured_secret(
    monkeypatch,
) -> None:
    captured: dict = {}

    async def _fake_post(client: httpx.AsyncClient, url: str, **kwargs: object) -> MagicMock:
        captured["content"] = kwargs["content"]
        captured["headers"] = kwargs["headers"]
        return _response(200)

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)
    monkeypatch.setattr(n8n_client.settings, "N8N_WEBHOOK_SECRET", _SIGNING_SECRET)
    client = N8nClient(base_url=_BASE)
    await client.trigger_webhook("/webhook/x", {"b": 2, "a": 1})

    body = captured["content"]
    headers = captured["headers"]
    assert body == b'{"a":1,"b":2}'
    timestamp = headers["X-AgencyOS-Timestamp"]
    nonce = headers["X-AgencyOS-Nonce"]
    expected = hmac.new(
        _SIGNING_SECRET.encode(),
        timestamp.encode() + b"." + nonce.encode() + b"." + body,
        hashlib.sha256,
    ).hexdigest()
    assert headers["X-AgencyOS-Signature"] == expected
    assert _SIGNING_SECRET not in repr(headers)


async def test_trigger_webhook_adds_metadata_headers(monkeypatch) -> None:
    captured: dict = {}

    async def _fake_post(client: httpx.AsyncClient, url: str, **kwargs: object) -> MagicMock:
        captured["headers"] = kwargs["headers"]
        return _response(200)

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)
    client = N8nClient(base_url=_BASE)
    await client.trigger_webhook(
        "/webhook/x",
        {"a": 1},
        metadata={
            "organization_id": "org-1",
            "actor_id": "actor-1",
            "workflow_id": "workflow-1",
            "execution_id": "execution-1",
            "idempotency_key": "idem-1",
        },
    )

    headers = captured["headers"]
    assert headers["X-AgencyOS-Org-Id"] == "org-1"
    assert headers["X-AgencyOS-Actor-Id"] == "actor-1"
    assert headers["X-AgencyOS-Workflow-Id"] == "workflow-1"
    assert headers["X-AgencyOS-Execution-Id"] == "execution-1"
    assert headers["X-AgencyOS-Idempotency-Key"] == "idem-1"


async def test_trigger_webhook_retries_transient_5xx(monkeypatch) -> None:
    post = AsyncMock(
        side_effect=[_response(500), _response(503), _response(200, payload={"ok": True})]
    )
    sleep = AsyncMock()
    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    monkeypatch.setattr(n8n_client, "_sleep_backoff", sleep)

    client = N8nClient(base_url=_BASE)
    assert await client.trigger_webhook("/webhook/x", {"a": 1}) == {"ok": True}
    assert post.await_count == 3
    assert sleep.await_count == 2


async def test_trigger_webhook_uses_fresh_nonce_and_signature_per_retry(monkeypatch) -> None:
    post = AsyncMock(side_effect=[_response(500), _response(200)])
    sleep = AsyncMock()
    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    monkeypatch.setattr(n8n_client, "_sleep_backoff", sleep)
    monkeypatch.setattr(n8n_client.settings, "N8N_WEBHOOK_SECRET", _SIGNING_SECRET)

    client = N8nClient(base_url=_BASE)
    assert await client.trigger_webhook("/webhook/x", {"a": 1}) == {"ok": True}

    first, second = (call.kwargs["headers"] for call in post.await_args_list)
    assert first["X-AgencyOS-Nonce"] != second["X-AgencyOS-Nonce"]
    assert first["X-AgencyOS-Signature"] != second["X-AgencyOS-Signature"]


async def test_trigger_webhook_retries_timeout(monkeypatch) -> None:
    post = AsyncMock(side_effect=[httpx.ReadTimeout("timed out"), _response(200)])
    sleep = AsyncMock()
    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    monkeypatch.setattr(n8n_client, "_sleep_backoff", sleep)

    client = N8nClient(base_url=_BASE)
    assert await client.trigger_webhook("/webhook/x", {"a": 1}) == {"ok": True}
    assert post.await_count == 2
    sleep.assert_awaited_once_with(1)


async def test_trigger_webhook_does_not_retry_non_transient_4xx(monkeypatch) -> None:
    post = AsyncMock(return_value=_response(400, b'{"error":"bad request"}'))
    sleep = AsyncMock()
    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    monkeypatch.setattr(n8n_client, "_sleep_backoff", sleep)

    client = N8nClient(base_url=_BASE)
    with pytest.raises(N8nHttpError) as exc_info:
        await client.trigger_webhook("/webhook/x", {"a": 1})
    assert exc_info.value.status_code == 400
    post.assert_awaited_once()
    sleep.assert_not_awaited()


async def test_health_check_returns_true_on_200(monkeypatch) -> None:
    monkeypatch.setattr(httpx.AsyncClient, "get", AsyncMock(return_value=_response(200)))
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


async def test_trigger_webhook_requires_base_url(monkeypatch) -> None:
    monkeypatch.setattr(n8n_client.settings, "N8N_BASE_URL", "")
    client = N8nClient(base_url="")
    with pytest.raises(ValueError, match="N8N_BASE_URL"):
        await client.trigger_webhook("/webhook/x", {"a": 1})


async def test_trigger_webhook_raises_sanitized_http_error(monkeypatch) -> None:
    monkeypatch.setattr(
        httpx.AsyncClient,
        "post",
        AsyncMock(return_value=_response(500, b"x-account-error: 'boom' with a long traceback")),
    )
    monkeypatch.setattr(n8n_client, "_sleep_backoff", AsyncMock())
    client = N8nClient(base_url=_BASE, api_key="k")
    with pytest.raises(N8nHttpError) as exc_info:
        await client.trigger_webhook("/webhook/x", {"a": 1})

    error = exc_info.value
    raw_body = "x-account-error: 'boom' with a long traceback"
    assert error.status_code == 500
    assert error.body == "<redacted provider response>"
    assert raw_body not in repr(error)
    assert raw_body not in repr(error.diagnostics)
    assert error.diagnostics["provider"] == "n8n"
    assert error.diagnostics["status_code"] == 500
    assert _BASE not in repr(error.diagnostics)


async def test_trigger_webhook_redacts_sensitive_body(monkeypatch) -> None:
    monkeypatch.setattr(
        httpx.AsyncClient,
        "post",
        AsyncMock(
            return_value=_response(
                400, b'{"error": "unauthorized", "x-n8n-api-key": "supersecret"}'
            )
        ),
    )
    client = N8nClient(base_url=_BASE)
    with pytest.raises(N8nHttpError) as exc_info:
        await client.trigger_webhook("/webhook/x", {"a": 1})

    assert "supersecret" not in repr(exc_info.value)
    assert exc_info.value.body == "<redacted provider response>"


async def test_trigger_webhook_truncates_large_body(monkeypatch) -> None:
    monkeypatch.setattr(
        httpx.AsyncClient, "post", AsyncMock(return_value=_response(502, b"z" * 5000))
    )
    monkeypatch.setattr(n8n_client, "_sleep_backoff", AsyncMock())
    client = N8nClient(base_url=_BASE)
    with pytest.raises(N8nHttpError) as exc_info:
        await client.trigger_webhook("/webhook/x", {"a": 1})

    assert exc_info.value.body == "<redacted provider response>"


async def test_transport_failure_error_never_exposes_host_or_api_key(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        httpx.AsyncClient,
        "post",
        AsyncMock(side_effect=httpx.ConnectError("connect failed to secret-host")),
    )
    monkeypatch.setattr(n8n_client, "_sleep_backoff", AsyncMock())
    client = N8nClient(base_url=_BASE, api_key="supersecret-key")
    with pytest.raises(N8nHttpError) as exc_info:
        await client.trigger_webhook("/webhook/x", {"a": 1})

    error = exc_info.value
    assert error.status_code == 503
    assert error.url == "/webhook/x"
    assert _BASE not in repr(error.diagnostics)
    assert "supersecret" not in repr(error.diagnostics)
    assert "secret-host" not in error.body


def test_get_n8n_client_factory(monkeypatch) -> None:
    monkeypatch.setattr(n8n_client.settings, "N8N_BASE_URL", _BASE)
    client = get_n8n_client()
    assert isinstance(client, N8nClient)
