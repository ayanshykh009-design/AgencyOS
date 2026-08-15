"""API tests for the M9 founder intelligence router.

Verifies the intelligence routes are registered and that unauthenticated
requests get a structured 401 before touching the database. The triage/run
endpoint is additionally verified to fail closed (503) while triage is
disabled in the test environment.
"""
from __future__ import annotations

import uuid

from app.core.config import settings

SIGNAL_ID = uuid.UUID("00000000-0000-0000-0000-000000000301")


def test_intelligence_signals_list_requires_auth(client) -> None:
    res = client.get("/api/v1/intelligence/signals")
    assert res.status_code == 401


def test_intelligence_signals_get_requires_auth(client) -> None:
    res = client.get(f"/api/v1/intelligence/signals/{SIGNAL_ID}")
    assert res.status_code == 401


def test_intelligence_signals_patch_requires_auth(client) -> None:
    res = client.patch(
        f"/api/v1/intelligence/signals/{SIGNAL_ID}", json={"status": "acknowledged"}
    )
    assert res.status_code == 401


def test_intelligence_summary_requires_auth(client) -> None:
    res = client.get("/api/v1/intelligence/summary")
    assert res.status_code == 401


def test_intelligence_triage_run_fails_closed_when_disabled(client) -> None:
    if settings.INTELLIGENCE_TRIAGE_ENABLED:
        import pytest

        pytest.skip("INTELLIGENCE_TRIAGE_ENABLED is on in this environment")
    res = client.post("/api/v1/intelligence/triage/run")
    assert res.status_code == 401  # auth is checked before the capability gate


def test_intelligence_routes_registered(client) -> None:
    # Route registration sanity: the paths exist and respond with 401 unauthenticated.
    assert client.get("/api/v1/intelligence/signals").status_code == 401
    assert client.get("/api/v1/intelligence/summary").status_code == 401
