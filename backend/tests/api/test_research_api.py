"""API tests for the research endpoints.

Full CRUD needs a live DB + authenticated user (covered by integration),
so here we verify the routes are registered and guarded: unauthenticated
requests must receive a structured 401 without touching the database, and
VIEWER must be rejected (403) on every mutating/spend-bearing route
(B-5: authenticated != authorized).
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

from app.api.deps import get_current_user
from app.core.permissions import Permission, has_permission
from app.main import app
from app.models.enums import UserRole

LEAD_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")


def test_trigger_research_requires_auth(client) -> None:
    res = client.post(f"/api/v1/research/{LEAD_ID}")
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "auth.missing_token"


def test_get_research_requires_auth(client) -> None:
    res = client.get(f"/api/v1/research/{LEAD_ID}")
    assert res.status_code == 401


def test_update_research_requires_auth(client) -> None:
    res = client.patch(f"/api/v1/research/{LEAD_ID}", json={"status": "completed"})
    assert res.status_code == 401


def test_delete_research_requires_auth(client) -> None:
    res = client.delete(f"/api/v1/research/{LEAD_ID}")
    assert res.status_code == 401


# -- permission matrix ------------------------------------------------------


def test_research_trigger_requires_ai_run() -> None:
    """Triggering research spends AI budget: VIEWER must not hold AI_RUN."""
    assert not has_permission(UserRole.VIEWER, Permission.AI_RUN)
    assert has_permission(UserRole.MEMBER, Permission.AI_RUN)
    assert has_permission(UserRole.MANAGER, Permission.AI_RUN)


def test_research_read_allows_viewer() -> None:
    assert has_permission(UserRole.VIEWER, Permission.LEAD_READ)


def test_research_mutation_requires_lead_write() -> None:
    assert not has_permission(UserRole.VIEWER, Permission.LEAD_WRITE)
    assert has_permission(UserRole.MEMBER, Permission.LEAD_WRITE)


# Positive (allowed-role reaches the handler) paths require a live database;
# they are covered by the permission-matrix assertions above and the
# integration suite in CI. The regression that matters for B-5 is the viewer
# rejection (403) verified below without a DB.


# -- viewer must be rejected (403) on mutations/spend -----------------------


def _as_viewer():
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=uuid.uuid4(), organization_id=uuid.uuid4(), role=UserRole.VIEWER
    )


def test_trigger_research_forbidden_for_viewer(client) -> None:
    _as_viewer()
    try:
        res = client.post(f"/api/v1/research/{LEAD_ID}")
        assert res.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_update_research_forbidden_for_viewer(client) -> None:
    _as_viewer()
    try:
        res = client.patch(f"/api/v1/research/{LEAD_ID}", json={"status": "completed"})
        assert res.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_delete_research_forbidden_for_viewer(client) -> None:
    _as_viewer()
    try:
        res = client.delete(f"/api/v1/research/{LEAD_ID}")
        assert res.status_code == 403
    finally:
        app.dependency_overrides.clear()
