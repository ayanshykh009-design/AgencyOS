"""Tests for the health/liveness endpoints and error envelope."""
from app.schemas.health import HealthResponse


def test_liveness_returns_ok(client) -> None:
    res = client.get("/api/v1/health/live")
    assert res.status_code == 200
    body = HealthResponse.model_validate(res.json())
    assert body.status == "ok"
    assert body.service == "AgencyOS API"


def test_health_alias_is_backward_compatible(client) -> None:
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_unknown_route_returns_structured_404(client) -> None:
    res = client.get("/api/v1/does-not-exist")
    assert res.status_code == 404
    body = res.json()
    assert body["error"]["code"] == "not_found"
    assert body["error"]["message"]


def test_csp_header_applied_by_default(client) -> None:
    res = client.get("/api/v1/health/live")
    assert res.status_code == 200
    csp = res.headers["content-security-policy"]
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'self'" in csp


def test_csp_header_suppressed_when_disabled(client, monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "ENABLE_CSP", False)
    res = client.get("/api/v1/health/live")
    assert res.status_code == 200
    assert "content-security-policy" not in res.headers
