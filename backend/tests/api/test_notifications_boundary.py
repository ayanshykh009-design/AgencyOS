"""Notification trust-boundary regression tests (API + service level).

Founder-approved closure (2026-11): notification creation is a trusted
internal concern only.

* There is **no** HTTP notification-create endpoint. Every ``NotificationType``
  (``SYSTEM``, ``APPROVAL_REQUEST``, ``APPROVAL_RESULT``, ``WORKFLOW_EVENT``,
  ``AGENT_EVENT``, ``BRIEFING``, ``INSIGHT``) is a system/worker/agent/
  approval origin, so a user-writable create surface would let any
  authenticated member fabricate a privileged notification in another user's
  inbox — a phishing primitive. The previous ``POST /api/v1/notifications``
  route has been removed; these tests pin it shut.
* The trusted creation paths are internal only:
  - ``app/communication/inapp_provider.py`` (M6 delivery worker) constructs
    the row directly (covered by ``tests/unit/test_delivery_providers.py``),
  - ``NotificationService.create`` for internal services (covered here at
    service level).
* Remaining trust assumption (documented): internal services and the worker
  vouch for recipient/type/action_url themselves — no endpoint-level rule
  can protect direct internal callers, by design.
* Recipient remains server-authoritative everywhere: inbox rows are read and
  marked read strictly per ``(organization_id, user_id)``.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.api.v1.endpoints import notifications as notifications_module
from app.main import app
from app.models.enums import NotificationType, UserRole
from app.services.notification_service import NotificationService

NOTIFICATIONS_PREFIX = "/api/v1/notifications"


# -- the create surface stays closed for every identity ----------------------


@pytest.mark.parametrize("role", list(UserRole))
def test_post_notifications_is_gone_for_every_role(
    client: TestClient, role: UserRole
) -> None:
    """Any authenticated user (including OWNER) gets 404: no HTTP creation."""
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=uuid.uuid4(), organization_id=uuid.uuid4(), role=role
    )
    try:
        res = client.post(
            NOTIFICATIONS_PREFIX,
            json={
                "organization_id": str(uuid.uuid4()),
                "user_id": str(uuid.uuid4()),
                "type": "system",
                "title": "Hi",
                "body": "hello",
            },
        )
    finally:
        app.dependency_overrides.clear()
    # The path exists (GET listing), but POST is not an allowed method:
    # creation has no HTTP surface. 405, not 201/403 — pinned deliberately.
    assert res.status_code == 405, res.text


def test_post_notifications_is_gone_for_anonymous(client: TestClient) -> None:
    res = client.post(
        NOTIFICATIONS_PREFIX,
        json={
            "organization_id": str(uuid.uuid4()),
            "type": "system",
            "title": "Hi",
            "body": "hello",
        },
    )
    # 405 (method not allowed) — the creation surface is gone entirely.
    assert res.status_code == 405, res.text


def test_openapi_has_no_notification_create_route() -> None:
    spec = app.openapi()
    methods = spec["paths"].get(NOTIFICATIONS_PREFIX, {})
    assert "post" not in methods
    # The read/mark-read surface must remain intact.
    for path, expected in [
        (NOTIFICATIONS_PREFIX, {"get"}),
        (f"{NOTIFICATIONS_PREFIX}/unread-count", {"get"}),
        (f"{NOTIFICATIONS_PREFIX}/counts", {"get"}),
        (f"{NOTIFICATIONS_PREFIX}/{{notification_id}}", {"get", "patch"}),
        (f"{NOTIFICATIONS_PREFIX}/{{notification_id}}/read", {"post"}),
    ]:
        assert set(spec["paths"].get(path, {})) == expected, path


def test_notifications_router_declares_no_create_route() -> None:
    create_routes = [
        route
        for route in notifications_module.router.routes
        if isinstance(route, APIRoute) and route.path == "" and "POST" in route.methods
    ]
    assert create_routes == []


# -- trusted internal creation still works -----------------------------------


class _FakeNotificationRepository:
    def __init__(self, session: Any) -> None:
        self.added: list[Any] = []

    def add(self, notification: Any) -> None:
        self.added.append(notification)


def test_trusted_internal_service_create_still_works(monkeypatch) -> None:
    """``NotificationService.create`` remains the trusted internal primitive
    (used by internal services; the M6 worker constructs rows directly)."""
    from types import SimpleNamespace

    import app.services.notification_service as service_module

    async def _no_commit(session: Any) -> None:
        return None

    monkeypatch.setattr(service_module, "commit_with_retry", _no_commit)

    service = NotificationService(SimpleNamespace())  # type: ignore[arg-type]
    service._notifications = _FakeNotificationRepository(None)

    import asyncio

    created = asyncio.run(
        service.create(
            uuid.uuid4(),
            user_id=uuid.uuid4(),
            type=NotificationType.SYSTEM,
            title="Hi",
            body="hello",
            action_url="/inbox",
            metadata_={"k": 1},
        )
    )

    assert created.type is NotificationType.SYSTEM
    assert created.action_url == "/inbox"
    assert len(service._notifications.added) == 1  # type: ignore[attr-defined]
