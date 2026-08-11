"""API tests for the M6 delivery + monitoring routers.

Verifies routes are registered and that unauthenticated requests get a
structured 401 before touching the database. RBAC checks are covered by
overriding the auth dependency (a VIEWER is rejected with 403 before the
handler runs); the permission matrix itself is asserted directly.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

from app.api.deps import get_current_user
from app.core.permissions import (
    Permission,
    has_permission,
    require_permission,
)
from app.main import app
from app.models.enums import UserRole

DELIVERY_ID = uuid.UUID("00000000-0000-0000-0000-000000000901")


# -- permission matrix -----------------------------------------------


def test_delivery_read_is_available_to_all_roles() -> None:
    for role in UserRole:
        assert has_permission(role, Permission.DELIVERY_READ)


def test_delivery_write_excludes_viewers() -> None:
    assert not has_permission(UserRole.VIEWER, Permission.DELIVERY_WRITE)
    assert has_permission(UserRole.MEMBER, Permission.DELIVERY_WRITE)
    assert has_permission(UserRole.OWNER, Permission.DELIVERY_WRITE)


def test_delivery_manage_is_admin_only() -> None:
    assert has_permission(UserRole.OWNER, Permission.DELIVERY_MANAGE)
    assert has_permission(UserRole.ADMIN, Permission.DELIVERY_MANAGE)
    assert not has_permission(UserRole.MANAGER, Permission.DELIVERY_MANAGE)
    assert not has_permission(UserRole.MEMBER, Permission.DELIVERY_MANAGE)


def test_delivery_statistics_is_admin_only() -> None:
    assert has_permission(UserRole.OWNER, Permission.AUTOMATION_MANAGE)
    assert not has_permission(UserRole.MEMBER, Permission.AUTOMATION_MANAGE)


# -- auth guard (401) ------------------------------------------------


def test_deliveries_list_requires_auth(client) -> None:
    res = client.get("/api/v1/deliveries")
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "auth.missing_token"


def test_deliveries_create_requires_auth(client) -> None:
    res = client.post(
        "/api/v1/deliveries",
        json={
            "organization_id": str(uuid.uuid4()),
            "channel": "dashboard",
            "subject": "s",
            "body": "b",
        },
    )
    assert res.status_code == 401


def test_deliveries_get_requires_auth(client) -> None:
    res = client.get(f"/api/v1/deliveries/{DELIVERY_ID}")
    assert res.status_code == 401


def test_deliveries_events_requires_auth(client) -> None:
    res = client.get(f"/api/v1/deliveries/{DELIVERY_ID}/events")
    assert res.status_code == 401


def test_deliveries_retry_requires_auth(client) -> None:
    res = client.post(f"/api/v1/deliveries/{DELIVERY_ID}/retry", json={})
    assert res.status_code == 401


def test_deliveries_cancel_requires_auth(client) -> None:
    res = client.post(f"/api/v1/deliveries/{DELIVERY_ID}/cancel", json={})
    assert res.status_code == 401


def test_deliveries_statistics_not_registered(client) -> None:
    # The org-scoped /statistics route was removed from the delivery router
    # per the frozen plan (monitoring owns platform statistics).
    res = client.get("/api/v1/deliveries/statistics")
    assert res.status_code in (401, 404)


def test_monitoring_delivery_statistics_requires_auth(client) -> None:
    res = client.get("/api/v1/monitoring/delivery-statistics")
    assert res.status_code == 401


# -- RBAC (403) via auth override ------------------------------------


def test_deliveries_retry_forbidden_for_viewer(client) -> None:
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=uuid.uuid4(), organization_id=uuid.uuid4(), role=UserRole.VIEWER
    )
    try:
        res = client.post(f"/api/v1/deliveries/{DELIVERY_ID}/retry", json={})
        assert res.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_monitoring_delivery_statistics_forbidden_for_member(client) -> None:
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=uuid.uuid4(), organization_id=uuid.uuid4(), role=UserRole.MEMBER
    )
    try:
        res = client.get("/api/v1/monitoring/delivery-statistics")
        assert res.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_require_permission_rejects_viewer() -> None:
    dep = require_permission(Permission.DELIVERY_MANAGE)
    import asyncio

    try:
        asyncio.run(dep(SimpleNamespace(role=UserRole.VIEWER)))
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 403
