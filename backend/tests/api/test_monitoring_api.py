"""API tests for the monitoring router (B-2 tenant isolation + RBAC).

Database-free: positive paths are proven by asserting the handler forwards
``current_user.organization_id`` into the service (mocked at the endpoint
module). Negative paths (RBAC 403) use the dependency override pattern from
``test_leads_rbac.py``. The permission matrix is asserted directly.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.api.deps import get_current_user
from app.core.permissions import (
    Permission,
    has_permission,
)
from app.main import app
from app.models.enums import UserRole

ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


# -- permission matrix ------------------------------------------------------


def test_automation_read_allows_all_roles_but_data_is_org_scoped() -> None:
    for role in UserRole:
        assert has_permission(role, Permission.AUTOMATION_READ)


def test_automation_manage_is_admin_only() -> None:
    for role in (UserRole.OWNER, UserRole.ADMIN):
        assert has_permission(role, Permission.AUTOMATION_MANAGE)
    for role in (UserRole.MANAGER, UserRole.MEMBER, UserRole.SALES_AGENT, UserRole.VIEWER):
        assert not has_permission(role, Permission.AUTOMATION_MANAGE)


# -- auth guards (401) ------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/monitoring/operational/summary",
        "/api/v1/monitoring/execution-statistics",
        "/api/v1/monitoring/delivery-statistics",
        "/api/v1/monitoring/worker-statistics",
        "/api/v1/monitoring/schedule-statistics",
        "/api/v1/monitoring/retention-statistics",
        "/api/v1/monitoring/automation-lifecycle",
        "/api/v1/monitoring/heartbeat-visibility",
        "/api/v1/monitoring/execution-timeline",
        "/api/v1/monitoring/execution-history",
        "/api/v1/monitoring/queue-status",
        "/api/v1/monitoring/monitoring-information",
    ],
)
def test_monitoring_endpoints_require_auth(client, path: str) -> None:
    res = client.get(path)
    assert res.status_code == 401


# -- RBAC 403 for non-admin on admin-only endpoints -------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/monitoring/operational/summary",
        "/api/v1/monitoring/delivery-statistics",
        "/api/v1/monitoring/worker-statistics",
        "/api/v1/monitoring/schedule-statistics",
        "/api/v1/monitoring/retention-statistics",
        "/api/v1/monitoring/heartbeat-visibility",
    ],
)
def test_admin_only_monitoring_endpoints_reject_member(client, path: str) -> None:
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=uuid.uuid4(), organization_id=ORG_ID, role=UserRole.MEMBER
    )
    try:
        res = client.get(path)
        assert res.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/monitoring/operational/summary",
        "/api/v1/monitoring/delivery-statistics",
        "/api/v1/monitoring/worker-statistics",
    ],
)
def test_admin_only_monitoring_endpoints_reject_viewer(client, path: str) -> None:
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=uuid.uuid4(), organization_id=ORG_ID, role=UserRole.VIEWER
    )
    try:
        res = client.get(path)
        assert res.status_code == 403
    finally:
        app.dependency_overrides.clear()


# -- org-id forwarding (tenant isolation at the handler boundary) -----------


def _as(role: UserRole, org_id: uuid.UUID = ORG_ID) -> None:
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=uuid.uuid4(), organization_id=org_id, role=role
    )


def test_execution_statistics_forwards_caller_org_id(client) -> None:
    """B-2: the handler passes current_user.organization_id into the service."""
    captured: dict = {}

    class _RecordingService:
        def __init__(self, session) -> None:
            pass

        async def get_execution_statistics(self, organization_id, hours=24):
            captured["organization_id"] = organization_id
            captured["hours"] = hours
            return {
                "window_hours": hours,
                "counts_by_status": {},
                "counts_by_workflow": {},
                "counts_by_organization": {},
                "total_executions": 0,
            }

    _as(UserRole.MEMBER)
    with patch(
        "app.api.v1.endpoints.monitoring.OperationalMonitoringService", _RecordingService
    ):
        res = client.get("/api/v1/monitoring/execution-statistics?hours=24")
    try:
        assert res.status_code == 200
        assert captured["organization_id"] == ORG_ID
    finally:
        app.dependency_overrides.clear()


def test_queue_status_forwards_caller_org_id(client) -> None:
    captured: dict = {}

    class _RecordingService:
        def __init__(self, session) -> None:
            pass

        async def get_queue_status(self, organization_id):
            captured["organization_id"] = organization_id
            return {
                "total_queued": 0,
                "total_running": 0,
                "total_pending": 0,
                "max_pending_per_org": 0,
                "organization_queues": [],
            }

    _as(UserRole.MEMBER)
    with patch(
        "app.api.v1.endpoints.monitoring.OperationalMonitoringService", _RecordingService
    ):
        res = client.get("/api/v1/monitoring/queue-status")
    try:
        assert res.status_code == 200
        assert captured["organization_id"] == ORG_ID
    finally:
        app.dependency_overrides.clear()


def test_execution_history_forwards_caller_org_id(client) -> None:
    captured: dict = {}

    class _RecordingService:
        def __init__(self, session) -> None:
            pass

        async def get_execution_history(
            self,
            organization_id,
            page=1,
            page_size=50,
            hours=24,
            status=None,
            workflow_name=None,
        ):
            captured["organization_id"] = organization_id
            return {"entries": [], "total": 0}

    _as(UserRole.MEMBER)
    with patch(
        "app.api.v1.endpoints.monitoring.OperationalMonitoringService", _RecordingService
    ):
        res = client.get("/api/v1/monitoring/execution-history")
    try:
        assert res.status_code == 200
        assert captured["organization_id"] == ORG_ID
    finally:
        app.dependency_overrides.clear()


def test_operational_summary_forwards_caller_org_id(client) -> None:
    captured: dict = {}

    class _RecordingService:
        def __init__(self, session) -> None:
            pass

        async def get_operational_summary(self, organization_id):
            captured["organization_id"] = organization_id
            return {
                "timestamp": "2026-01-01T00:00:00+00:00",
                "executions": {
                    "queued": 0,
                    "running": 0,
                    "completed": 0,
                    "failed": 0,
                    "timed_out": 0,
                    "cancelled": 0,
                    "retrying": 0,
                    "total_active": 0,
                },
                "events": {"last_24h": 0, "queued": 0, "consumed": 0, "fanout_truncated": 0},
                "workers": {"healthy": 0, "stale": 0, "total": 0, "health_percentage": 0.0},
                "automation": {
                    "enabled": True,
                    "paused": False,
                    "paused_by": None,
                    "paused_at": None,
                    "paused_reason": None,
                },
                "schedules": {
                    "queued": 0,
                    "failed": 0,
                    "skipped": 0,
                    "conflicts": 0,
                },
                "system": {
                    "database_connected": True,
                    "retention_enabled": False,
                    "worker_enabled": False,
                    "schedule_dispatcher_enabled": False,
                },
            }

    _as(UserRole.ADMIN)
    with patch(
        "app.api.v1.endpoints.monitoring.OperationalMonitoringService", _RecordingService
    ):
        res = client.get("/api/v1/monitoring/operational/summary")
    try:
        assert res.status_code == 200
        assert captured["organization_id"] == ORG_ID
    finally:
        app.dependency_overrides.clear()


def test_delivery_statistics_forwards_caller_org_id(client) -> None:
    captured: dict = {}

    class _RecordingDelivery:
        def __init__(self, session) -> None:
            pass

        async def platform_statistics(self, organization_id):
            captured["organization_id"] = organization_id
            return {
                "queued": 0,
                "processing": 0,
                "retrying": 0,
                "delivered": 0,
                "failed": 0,
                "cancelled": 0,
                "active": 0,
                "terminal": 0,
            }

    _as(UserRole.OWNER)
    with patch("app.services.delivery_service.DeliveryService", _RecordingDelivery):
        res = client.get("/api/v1/monitoring/delivery-statistics")
    try:
        assert res.status_code == 200
        assert captured["organization_id"] == ORG_ID
    finally:
        app.dependency_overrides.clear()


def test_automation_lifecycle_forwards_caller_org_id(client) -> None:
    captured: dict = {}

    class _RecordingService:
        def __init__(self, session) -> None:
            pass

        async def get_automation_lifecycle(self, organization_id):
            captured["organization_id"] = organization_id
            return {
                "automation_paused_events": 0,
                "automation_resumed_events": 0,
                "current_status": {
                    "enabled": True,
                    "paused_by": None,
                    "paused_at": None,
                    "paused_reason": None,
                },
            }

    _as(UserRole.MEMBER)
    with patch(
        "app.api.v1.endpoints.monitoring.OperationalMonitoringService", _RecordingService
    ):
        res = client.get("/api/v1/monitoring/automation-lifecycle")
    try:
        assert res.status_code == 200
        assert captured["organization_id"] == ORG_ID
    finally:
        app.dependency_overrides.clear()
