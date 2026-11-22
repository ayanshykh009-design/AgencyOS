"""Tests for inbound webhook authenticity, replay guard, and secret checks."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.api.v1.endpoints import webhooks
from app.api.v1.endpoints.webhooks import _check_secret
from app.core.errors import AppError
from app.main import create_app

_SECRET = "s3cret"
_ORG_SLUG = "acme"
_ORG_ID = uuid.uuid4()
_LEAD_ID = uuid.uuid4()
# Deliberately non-canonical JSON: the signature must cover these exact bytes.
_RAW_BODY = (
    b'{ "email" : "a@example.com", "organization_slug" : "acme", '
    b'"notes" : "raw  body with spaces" }'
)


def test_check_secret_accepts_matching_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.api.v1.endpoints.webhooks.settings.WEBHOOK_SECRET", "s3cret")
    _check_secret("s3cret")  # must not raise


def test_check_secret_rejects_wrong_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.api.v1.endpoints.webhooks.settings.WEBHOOK_SECRET", "s3cret")
    with pytest.raises(AppError) as exc_info:
        _check_secret("wrong")
    assert exc_info.value.status_code == 401
    assert exc_info.value.code == "webhook.invalid_secret"


def test_check_secret_rejects_missing_header(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.api.v1.endpoints.webhooks.settings.WEBHOOK_SECRET", "s3cret")
    with pytest.raises(AppError) as exc_info:
        _check_secret(None)
    assert exc_info.value.status_code == 401


def test_check_secret_unconfigured_raises_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.api.v1.endpoints.webhooks.settings.WEBHOOK_SECRET", "")
    with pytest.raises(AppError) as exc_info:
        _check_secret("anything")
    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "webhook.not_configured"


def _signature(raw: bytes, timestamp: str, nonce: str, secret: str = _SECRET) -> str:
    signed = timestamp.encode("ascii") + b"." + nonce.encode("ascii") + b"." + raw
    return hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()


def _signed_headers(
    raw: bytes,
    *,
    timestamp: str | None = None,
    nonce: str | None = None,
    signature: str | None | object = None,
    secret: str = _SECRET,
) -> dict[str, str]:
    ts = str(int(time.time())) if timestamp is None else timestamp
    n = "nonce-abcdef123456" if nonce is None else nonce
    sig = _signature(raw, ts, n, secret) if signature is None else str(signature)
    return {
        "X-AgencyOS-Webhook": secret,
        "X-AgencyOS-Timestamp": ts,
        "X-AgencyOS-Nonce": n,
        "X-AgencyOS-Signature": sig,
        "Content-Type": "application/json",
    }


def _client(
    monkeypatch: pytest.MonkeyPatch, *, app_env: str = "development"
) -> TestClient:
    """Build an isolated app with no DB/network and a clean local replay store."""
    monkeypatch.setattr(webhooks.settings, "WEBHOOK_SECRET", _SECRET)
    monkeypatch.setattr(webhooks.settings, "APP_ENV", app_env)
    monkeypatch.setattr(webhooks, "_replay_seen", {})
    monkeypatch.setattr(webhooks, "_replay_claims", {})

    app = create_app()

    async def _stub_db():
        yield MagicMock()

    app.dependency_overrides[get_db] = _stub_db
    monkeypatch.setattr(
        webhooks.OrganizationRepository,
        "get_by_slug",
        AsyncMock(return_value=SimpleNamespace(id=_ORG_ID)),
    )
    monkeypatch.setattr(webhooks, "activate_org", AsyncMock())

    service = MagicMock()
    service.duplicate_check = AsyncMock(return_value=[])
    service.create = AsyncMock(return_value=SimpleNamespace(id=_LEAD_ID))
    monkeypatch.setattr(webhooks, "LeadService", MagicMock(return_value=service))
    return TestClient(app, base_url="http://localhost", raise_server_exceptions=False)


_URL = "/api/v1/webhooks/leads"


def test_webhook_ingest_refuses_when_unconfigured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.api.v1.endpoints.webhooks.settings.WEBHOOK_SECRET", "")
    resp = client.post(
        _URL,
        json={"email": "a@example.com"},
        headers={"X-AgencyOS-Webhook": "x"},
    )
    assert resp.status_code == 503


def test_webhook_ingest_rejects_wrong_secret(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.api.v1.endpoints.webhooks.settings.WEBHOOK_SECRET", "s3cret")
    resp = client.post(
        _URL,
        json={"email": "a@example.com"},
        headers={"X-AgencyOS-Webhook": "nope"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "webhook.invalid_secret"


def test_webhook_ingest_accepts_signature_over_exact_raw_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_client = _client(monkeypatch)
    resp = test_client.post(_URL, content=_RAW_BODY, headers=_signed_headers(_RAW_BODY))
    assert resp.status_code == 201, resp.text
    assert resp.json() == {"lead_id": str(_LEAD_ID), "duplicate": False}


def test_webhook_ingest_rejects_canonicalized_body_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A signature over re-serialized JSON must fail: the wire bytes are signed."""
    test_client = _client(monkeypatch)
    canonical = json.dumps(
        json.loads(_RAW_BODY), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    resp = test_client.post(
        _URL, content=_RAW_BODY, headers=_signed_headers(canonical)
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "webhook.invalid_signature"


def test_webhook_ingest_rejects_missing_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_client = _client(monkeypatch)
    headers = _signed_headers(_RAW_BODY)
    headers.pop("X-AgencyOS-Signature")
    resp = test_client.post(_URL, content=_RAW_BODY, headers=headers)
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "webhook.invalid_signature"


def test_webhook_ingest_rejects_wrong_signature_and_does_not_leak_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_client = _client(monkeypatch)
    original = _signed_headers(_RAW_BODY)
    bad = ("0" if original["X-AgencyOS-Signature"][0] != "0" else "1") + original[
        "X-AgencyOS-Signature"
    ][1:]
    headers = {**original, "X-AgencyOS-Signature": bad}
    resp = test_client.post(_URL, content=_RAW_BODY, headers=headers)
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "webhook.invalid_signature"
    assert _SECRET not in resp.text
    assert bad not in resp.text


def test_webhook_ingest_rejects_stale_timestamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_client = _client(monkeypatch)
    stale = str(int(time.time()) - 3600)
    resp = test_client.post(
        _URL,
        content=_RAW_BODY,
        headers=_signed_headers(_RAW_BODY, timestamp=stale),
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "webhook.invalid_signature"


def test_webhook_ingest_rejects_malformed_nonce(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_client = _client(monkeypatch)
    resp = test_client.post(
        _URL,
        content=_RAW_BODY,
        headers=_signed_headers(_RAW_BODY, nonce="short"),
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "webhook.invalid_signature"


def test_webhook_ingest_rejects_replayed_nonce(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_client = _client(monkeypatch)
    headers = _signed_headers(_RAW_BODY)
    assert test_client.post(_URL, content=_RAW_BODY, headers=headers).status_code == 201
    replay = test_client.post(_URL, content=_RAW_BODY, headers=headers)
    assert replay.status_code == 409
    assert replay.json()["error"]["code"] == "webhook.replay_detected"


def test_webhook_releases_nonce_after_lead_creation_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed delivery must not burn its nonce for the sender's retry."""
    test_client = _client(monkeypatch)
    service = webhooks.LeadService.return_value  # type: ignore[attr-defined]
    service.create.side_effect = [
        RuntimeError("transient database failure"),
        SimpleNamespace(id=_LEAD_ID),
    ]
    headers = _signed_headers(_RAW_BODY)

    failed = test_client.post(_URL, content=_RAW_BODY, headers=headers)
    assert failed.status_code == 500
    assert webhooks._replay_seen == {}

    retried = test_client.post(_URL, content=_RAW_BODY, headers=headers)
    assert retried.status_code == 201
    assert retried.json() == {"lead_id": str(_LEAD_ID), "duplicate": False}
    assert service.create.await_count == 2


def test_deployed_webhook_releases_redis_reservation_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_client = _client(monkeypatch, app_env="staging")
    redis_client = SimpleNamespace(
        set=AsyncMock(return_value=True), eval=AsyncMock(return_value=1)
    )
    monkeypatch.setattr(webhooks, "get_redis", lambda: redis_client)
    service = webhooks.LeadService.return_value  # type: ignore[attr-defined]
    service.create.side_effect = RuntimeError("transient database failure")

    resp = test_client.post(
        _URL,
        content=_RAW_BODY,
        headers=_signed_headers(_RAW_BODY),
    )
    assert resp.status_code == 500
    assert redis_client.eval.await_count == 1
    eval_args = redis_client.eval.await_args.args
    assert eval_args[0] == webhooks._RELEASE_REPLAY_SCRIPT
    assert eval_args[1] == 1


def test_webhook_ingest_preserves_duplicate_lead_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_client = _client(monkeypatch)
    service = webhooks.LeadService.return_value  # type: ignore[attr-defined]
    service.duplicate_check.return_value = [SimpleNamespace(id=_LEAD_ID)]
    resp = test_client.post(_URL, content=_RAW_BODY, headers=_signed_headers(_RAW_BODY))
    assert resp.status_code == 201
    assert resp.json() == {"lead_id": str(_LEAD_ID), "duplicate": True}
    service.create.assert_not_awaited()


def test_deployed_webhook_replay_uses_shared_redis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_client = _client(monkeypatch, app_env="staging")
    redis_client = SimpleNamespace(set=AsyncMock(side_effect=[True, False]))
    monkeypatch.setattr(webhooks, "get_redis", lambda: redis_client)
    headers = _signed_headers(_RAW_BODY)
    assert test_client.post(_URL, content=_RAW_BODY, headers=headers).status_code == 201
    replay = test_client.post(_URL, content=_RAW_BODY, headers=headers)
    assert replay.status_code == 409
    assert redis_client.set.await_count == 2
    kwargs = redis_client.set.await_args.kwargs
    assert kwargs["nx"] is True
    assert kwargs["ex"] == webhooks.settings.WEBHOOK_REPLAY_TTL_SECONDS
    assert _ORG_SLUG not in str(redis_client.set.await_args.args)


def test_deployed_webhook_redis_failure_fails_closed_without_memory_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_client = _client(monkeypatch, app_env="staging")

    def _broken_redis():
        raise RuntimeError("bad REDIS_URL")

    monkeypatch.setattr(webhooks, "get_redis", _broken_redis)
    headers = _signed_headers(_RAW_BODY)
    for _ in range(2):
        resp = test_client.post(_URL, content=_RAW_BODY, headers=headers)
        assert resp.status_code == 503
        assert resp.json()["error"]["code"] == "webhook.replay_unavailable"
    assert webhooks._replay_seen == {}
