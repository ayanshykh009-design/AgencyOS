"""Tests for the inbound webhook endpoints and secret verification."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints.webhooks import _check_secret
from app.core.errors import AppError


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


def test_webhook_ingest_refuses_when_unconfigured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.api.v1.endpoints.webhooks.settings.WEBHOOK_SECRET", "")
    resp = client.post(
        "/api/v1/webhooks/leads",
        json={"email": "a@example.com"},
        headers={"X-AgencyOS-Webhook": "x"},
    )
    assert resp.status_code == 503


def test_webhook_ingest_rejects_wrong_secret(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.api.v1.endpoints.webhooks.settings.WEBHOOK_SECRET", "s3cret")
    resp = client.post(
        "/api/v1/webhooks/leads",
        json={"email": "a@example.com"},
        headers={"X-AgencyOS-Webhook": "nope"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "webhook.invalid_secret"
