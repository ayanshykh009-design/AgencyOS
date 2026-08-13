"""API tests for the M7 growth intelligence routers.

Verifies the growth analysis/recommendation/scenario/health-weight/forecast-run
routes are registered and that unauthenticated requests get a structured 401
before touching the database (full behavior needs a live DB + JWT; service
unit tests cover the transaction logic).
"""
from __future__ import annotations

import uuid

ANALYSIS_ID = uuid.UUID("00000000-0000-0000-0000-000000000201")
REC_ID = uuid.UUID("00000000-0000-0000-0000-000000000202")
SCENARIO_ID = uuid.UUID("00000000-0000-0000-0000-000000000203")


def test_growth_analyses_list_requires_auth(client) -> None:
    res = client.get("/api/v1/growth/analyses")
    assert res.status_code == 401


def test_growth_analyses_run_requires_auth(client) -> None:
    res = client.post(
        "/api/v1/growth/analyses/run",
        json={
            "analysis_type": "kpis",
            "period_start": "2026-01-01T00:00:00Z",
            "period_end": "2026-01-31T00:00:00Z",
        },
    )
    assert res.status_code == 401


def test_growth_analyses_run_all_requires_auth(client) -> None:
    res = client.post(
        "/api/v1/growth/analyses/run-all",
        json={
            "period_start": "2026-01-01T00:00:00Z",
            "period_end": "2026-01-31T00:00:00Z",
        },
    )
    assert res.status_code == 401


def test_growth_analyses_get_requires_auth(client) -> None:
    res = client.get(f"/api/v1/growth/analyses/{ANALYSIS_ID}")
    assert res.status_code == 401


def test_growth_recommendations_list_requires_auth(client) -> None:
    res = client.get("/api/v1/growth/recommendations")
    assert res.status_code == 401


def test_growth_recommendations_counts_requires_auth(client) -> None:
    res = client.get("/api/v1/growth/recommendations/counts")
    assert res.status_code == 401


def test_growth_recommendations_update_requires_auth(client) -> None:
    res = client.patch(f"/api/v1/growth/recommendations/{REC_ID}", json={"status": "applied"})
    assert res.status_code == 401


def test_growth_scenarios_list_requires_auth(client) -> None:
    res = client.get("/api/v1/growth/scenarios")
    assert res.status_code == 401


def test_growth_scenarios_create_requires_auth(client) -> None:
    res = client.post(
        "/api/v1/growth/scenarios",
        json={"name": "Double leads", "assumption_deltas": {"new_leads_delta": 2.0}},
    )
    assert res.status_code == 401


def test_growth_scenarios_get_requires_auth(client) -> None:
    res = client.get(f"/api/v1/growth/scenarios/{SCENARIO_ID}")
    assert res.status_code == 401


def test_growth_scenarios_delete_requires_auth(client) -> None:
    res = client.delete(f"/api/v1/growth/scenarios/{SCENARIO_ID}")
    assert res.status_code == 401


def test_growth_health_weights_get_requires_auth(client) -> None:
    res = client.get("/api/v1/growth/health-weights")
    assert res.status_code == 401


def test_growth_health_weights_create_requires_auth(client) -> None:
    res = client.post(
        "/api/v1/growth/health-weights",
        json={"weights": {"pipeline_health": 0.5, "activity_level": 0.5}},
    )
    assert res.status_code == 401


def test_growth_forecast_run_requires_auth(client) -> None:
    res = client.post(
        "/api/v1/growth/forecasts/run",
        json={
            "method": "moving_average",
            "period_start": "2026-01-01T00:00:00Z",
            "period_end": "2026-01-31T00:00:00Z",
            "horizon_start": "2026-02-01T00:00:00Z",
            "horizon_end": "2026-03-03T00:00:00Z",
        },
    )
    assert res.status_code == 401
