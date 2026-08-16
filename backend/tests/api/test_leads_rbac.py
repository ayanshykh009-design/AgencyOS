"""RBAC regression tests for lead + export endpoints (Phase 1/2/4 hardening).

Leads endpoints previously had no ``require_permission`` guard, so a VIEWER (read
only per the permission matrix) could create/update/delete leads. Exports were
guarded by ``LEAD_READ`` (all roles) instead of ``EXPORT`` (managers only),
exposing lead PII to viewer-level callers.

These tests override the auth dependency so they run without a database: the
``require_permission`` dependency executes before the handler, so 403 responses
are produced without touching the DB.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

from app.api.deps import get_current_user
from app.core.permissions import Permission, has_permission
from app.main import app
from app.models.enums import UserRole

LEAD_ID = uuid.UUID("00000000-0000-0000-0000-00000000a001")


# -- permission matrix ------------------------------------------------------


def test_lead_write_excludes_viewer() -> None:
    assert not has_permission(UserRole.VIEWER, Permission.LEAD_WRITE)
    assert has_permission(UserRole.MEMBER, Permission.LEAD_WRITE)
    assert has_permission(UserRole.MANAGER, Permission.LEAD_WRITE)


def test_lead_delete_is_manage_only() -> None:
    assert not has_permission(UserRole.VIEWER, Permission.LEAD_DELETE)
    assert not has_permission(UserRole.MEMBER, Permission.LEAD_DELETE)
    assert has_permission(UserRole.MANAGER, Permission.LEAD_DELETE)


def test_export_is_manage_only() -> None:
    assert not has_permission(UserRole.VIEWER, Permission.EXPORT)
    assert has_permission(UserRole.OWNER, Permission.EXPORT)


# -- viewer must be rejected (403) on mutations -----------------------------


def test_create_lead_forbidden_for_viewer(client) -> None:
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=uuid.uuid4(), organization_id=uuid.uuid4(), role=UserRole.VIEWER
    )
    try:
        res = client.post("/api/v1/leads", json={"first_name": "A", "last_name": "B"})
        assert res.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_update_lead_forbidden_for_viewer(client) -> None:
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=uuid.uuid4(), organization_id=uuid.uuid4(), role=UserRole.VIEWER
    )
    try:
        res = client.patch(f"/api/v1/leads/{LEAD_ID}", json={"first_name": "C"})
        assert res.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_delete_lead_forbidden_for_viewer(client) -> None:
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=uuid.uuid4(), organization_id=uuid.uuid4(), role=UserRole.VIEWER
    )
    try:
        res = client.delete(f"/api/v1/leads/{LEAD_ID}")
        assert res.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_export_leads_forbidden_for_viewer(client) -> None:
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=uuid.uuid4(), organization_id=uuid.uuid4(), role=UserRole.VIEWER
    )
    try:
        res = client.get("/api/v1/exports/leads")
        assert res.status_code == 403
    finally:
        app.dependency_overrides.clear()


# -- allowed roles pass the RBAC gate (matrix) ------------------------------
# The synchronous-handler paths below require a live database, so the positive
# (allowed-role reaches the handler) case is covered by the permission matrix
# assertions above and the integration suite in CI. The regression that matters
# for this fix is the viewer rejection (403) verified above without a DB.
