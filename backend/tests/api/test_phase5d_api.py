"""API tests for the Phase 5D (M3) backend routers.

Verifies routes are registered and that unauthenticated requests get a
structured 401 before touching the database (full behavior needs a live DB +
JWT — the schema-level contract is covered by the service unit tests).
"""

from __future__ import annotations

import uuid

LEAD_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
RUN_ID = uuid.UUID("00000000-0000-0000-0000-000000000202")
MEMORY_ID = uuid.UUID("00000000-0000-0000-0000-000000000101")
NOTIFY_ID = uuid.UUID("00000000-0000-0000-0000-000000000003")
REQ_ID = uuid.UUID("00000000-0000-0000-0000-000000000004")
INSIGHT_ID = uuid.UUID("00000000-0000-0000-0000-000000000006")
FORECAST_ID = uuid.UUID("00000000-0000-0000-0000-000000000008")


def test_agents_states_requires_auth(client) -> None:
    res = client.get("/api/v1/agents/states")
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "auth.missing_token"


def test_agents_runs_requires_auth(client) -> None:
    res = client.get("/api/v1/agents/runs")
    assert res.status_code == 401


def test_agents_runs_create_requires_auth(client) -> None:
    res = client.post(
        "/api/v1/agents/runs",
        json={"agent_name": "outreach-agent", "trigger": "manual"},
    )
    assert res.status_code == 401


def test_agents_runs_update_requires_auth(client) -> None:
    res = client.patch(
        f"/api/v1/agents/runs/{RUN_ID}", json={"status": "succeeded"}
    )
    assert res.status_code == 401


# -- memory ----------------------------------------------------------


def test_memory_list_requires_auth(client) -> None:
    res = client.get("/api/v1/memory")
    assert res.status_code == 401


def test_memory_create_requires_auth(client) -> None:
    res = client.post(
        "/api/v1/memory",
        json={
            "organization_id": str(LEAD_ID),
            "scope": "conversation",
            "content": "remember this",
        },
    )
    assert res.status_code == 401


def test_memory_knowledge_search_requires_auth(client) -> None:
    res = client.get("/api/v1/memory/knowledge/search?q=lead")
    assert res.status_code == 401


def test_memory_delete_requires_auth(client) -> None:
    res = client.delete(f"/api/v1/memory/{MEMORY_ID}")
    assert res.status_code == 401


# -- notifications ---------------------------------------------------


def test_notifications_list_requires_auth(client) -> None:
    res = client.get("/api/v1/notifications")
    assert res.status_code == 401


def test_notifications_unread_count_requires_auth(client) -> None:
    res = client.get("/api/v1/notifications/unread-count")
    assert res.status_code == 401


def test_notifications_counts_requires_auth(client) -> None:
    res = client.get("/api/v1/notifications/counts")
    assert res.status_code == 401


def test_notifications_create_requires_auth(client) -> None:
    res = client.post(
        "/api/v1/notifications",
        json={
            "organization_id": str(LEAD_ID),
            "type": "system",
            "title": "Hi",
            "body": "hello world",
        },
    )
    assert res.status_code == 401


def test_notifications_read_requires_auth(client) -> None:
    res = client.get(f"/api/v1/notifications/{NOTIFY_ID}")
    assert res.status_code == 401


def test_notifications_mark_read_requires_auth(client) -> None:
    res = client.post(f"/api/v1/notifications/{NOTIFY_ID}/read")
    assert res.status_code == 401


# -- approvals -------------------------------------------------------


def test_approvals_list_requires_auth(client) -> None:
    res = client.get("/api/v1/approvals")
    assert res.status_code == 401


def test_approvals_pending_count_requires_auth(client) -> None:
    res = client.get("/api/v1/approvals/pending-count")
    assert res.status_code == 401


def test_approvals_create_requires_auth(client) -> None:
    res = client.post(
        "/api/v1/approvals",
        json={
            "organization_id": str(LEAD_ID),
            "title": "Ship the report",
        },
    )
    assert res.status_code == 401


def test_approvals_decide_requires_auth(client) -> None:
    res = client.post(
        f"/api/v1/approvals/{REQ_ID}/decision", json={"approve": True}
    )
    assert res.status_code == 401


def test_approvals_logs_requires_auth(client) -> None:
    res = client.get(f"/api/v1/approvals/{REQ_ID}/logs")
    assert res.status_code == 401


# -- founder ---------------------------------------------------------


def test_founder_briefings_requires_auth(client) -> None:
    res = client.get("/api/v1/founder/briefings")
    assert res.status_code == 401


def test_founder_insights_requires_auth(client) -> None:
    res = client.get("/api/v1/founder/insights")
    assert res.status_code == 401


def test_founder_insights_counts_requires_auth(client) -> None:
    res = client.get("/api/v1/founder/insights/counts")
    assert res.status_code == 401


def test_founder_insights_update_requires_auth(client) -> None:
    res = client.patch(f"/api/v1/founder/insights/{INSIGHT_ID}", json={"status": "dismissed"})
    assert res.status_code == 401


# -- growth ----------------------------------------------------------


def test_growth_metrics_requires_auth(client) -> None:
    res = client.get("/api/v1/growth/metrics?metric_type=revenue")
    assert res.status_code == 401


def test_growth_metrics_types_requires_auth(client) -> None:
    res = client.get("/api/v1/growth/metrics/types")
    assert res.status_code == 401


def test_growth_forecasts_requires_auth(client) -> None:
    res = client.get("/api/v1/growth/forecasts")
    assert res.status_code == 401


def test_growth_metrics_create_requires_auth(client) -> None:
    res = client.post(
        "/api/v1/growth/metrics",
        json={
            "organization_id": str(LEAD_ID),
            "metric_type": "revenue",
            "period_start": "2026-01-01T00:00:00Z",
            "period_end": "2026-02-01T00:00:00Z",
            "value": "1000",
        },
    )
    assert res.status_code == 401


# -- communications --------------------------------------------------


def test_communications_summary_requires_auth(client) -> None:
    res = client.get("/api/v1/communications/summary")
    assert res.status_code == 401
