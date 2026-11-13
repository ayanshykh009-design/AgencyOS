"""Delivery trust-boundary regression tests (API level).

``POST /api/v1/deliveries`` is the only client-facing path that can end up as
a notification inbox row (``channel=dashboard`` → ``InAppProvider.deliver``).
The founder-approved closure:

* ``channel="dashboard"`` (in-app) is **trusted-internal only** — the delivery
  worker and internal services enqueue those; a JWT user request is rejected
  with ``403 delivery.channel_trusted_only`` regardless of role. An ordinary
  enqueue would fabricate a privileged notification (SYSTEM /
  APPROVAL_REQUEST / agent / workflow) because the type and content come from
  the delivery payload.
* ``recipient_user_id`` is server-authoritative: a JWT user may only enqueue
  for *itself* (``403 delivery.recipient_not_allowed``) — cross-tenant and
  cross-user targeting are impossible; rejected requests never reach the
  service.
* ``action_url`` must be an application-relative path (allow-list grammar:
  single leading ``/``, no backslashes, no percent-encoding, no control
  characters, no scheme) — ``422 delivery.unsafe_action_url`` otherwise.

Remaining trust assumption (documented): internal service/worker callers of
``DeliveryService.enqueue`` (approvals, briefings, M6 recovery) vouch for
recipient and ``action_url`` themselves — endpoint rules cannot and must not
apply to them.

Retry/cancel remain admin-only (``delivery_manage``) — unchanged, covered by
``test_delivery_api.py``.
"""

from __future__ import annotations

import uuid
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models.enums import DeliveryChannel, DeliveryStatus, UserRole

ORG_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
OTHER_USER_ID = uuid.uuid4()
DELIVERY_ID = uuid.uuid4()
DELIVERIES_PREFIX = "/api/v1/deliveries"


def _delivery_row(
    channel: DeliveryChannel, recipient: uuid.UUID | None, action_url: str | None
) -> Any:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=DELIVERY_ID,
        organization_id=ORG_ID,
        channel=channel,
        recipient_user_id=recipient,
        notification_id=None,
        approval_request_id=None,
        subject="New meeting booked",
        body="A meeting was booked with a prospect.",
        action_url=action_url,
        status=DeliveryStatus.QUEUED,
        attempts=0,
        max_attempts=3,
        next_attempt_at=now,
        attempt_started_at=None,
        cancel_requested_at=None,
        cancelled_by_user_id=None,
        last_error=None,
        provider_metadata={},
        payload={},
        idempotency_key=None,
        scheduled_for=now,
        delivered_at=None,
        failed_at=None,
        cancelled_at=None,
        created_at=now,
        updated_at=now,
    )


class _FakeDeliveryService:
    calls: list[tuple[str, dict[str, Any]]] = []

    def __init__(self, session: Any) -> None:
        self._session = session

    async def enqueue(self, organization_id: uuid.UUID, **kwargs: Any) -> Any:
        self.calls.append(("enqueue", {"organization_id": str(organization_id), **{
            k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in kwargs.items()
        }}))
        return _delivery_row(
            kwargs.get("channel", DeliveryChannel.EMAIL),
            kwargs.get("recipient_user_id"),
            kwargs.get("action_url"),
        )


@pytest.fixture
def delivery_service(monkeypatch: pytest.MonkeyPatch) -> type[_FakeDeliveryService]:
    _FakeDeliveryService.calls = []
    monkeypatch.setattr(
        "app.api.v1.endpoints.deliveries.DeliveryService", _FakeDeliveryService
    )
    return _FakeDeliveryService


@pytest.fixture
def api_client(delivery_service: type[_FakeDeliveryService]) -> Generator[TestClient, None, None]:
    async def _stub_db() -> Any:
        yield SimpleNamespace()

    app.dependency_overrides[get_db] = _stub_db
    try:
        with TestClient(app, base_url="http://localhost") as client:
            yield client
    finally:
        app.dependency_overrides.clear()


@contextmanager
def _authenticated(role: UserRole) -> Generator[None, None, None]:
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=USER_ID, organization_id=ORG_ID, role=role
    )
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def _enqueue_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "organization_id": str(ORG_ID),
        "channel": "email",
        "recipient_user_id": str(USER_ID),
        "subject": "New meeting booked",
        "body": "A meeting was booked with a prospect.",
        "action_url": "/leads/1",
    }
    payload.update(overrides)
    return payload


# -- privileged channel: trusted-internal only ------------------------------


@pytest.mark.parametrize(
    "role",
    [
        UserRole.OWNER,
        UserRole.ADMIN,
        UserRole.MANAGER,
        UserRole.MEMBER,
        UserRole.SALES_AGENT,
    ],
)
def test_dashboard_channel_is_trusted_internal_only(api_client: TestClient, role: UserRole) -> None:
    """Even OWNER/ADMIN are ordinary JWT users for this rule: in-app
    notification creation never happens through the HTTP surface."""
    with _authenticated(role):
        res = api_client.post(
            DELIVERIES_PREFIX, json=_enqueue_payload(channel="dashboard")
        )
    assert res.status_code == 403, res.text
    assert res.json()["error"]["code"] == "delivery.channel_trusted_only"
    assert _FakeDeliveryService.calls == []


def test_dashboard_channel_rejection_precedes_other_rules(api_client: TestClient) -> None:
    with _authenticated(UserRole.MEMBER):
        res = api_client.post(
            DELIVERIES_PREFIX,
            json=_enqueue_payload(
                channel="dashboard",
                recipient_user_id=str(OTHER_USER_ID),
                action_url="https://attacker.example",
            ),
        )
    assert res.status_code == 403, res.text
    assert res.json()["error"]["code"] == "delivery.channel_trusted_only"
    assert _FakeDeliveryService.calls == []


# -- recipient is server-authoritative --------------------------------------


def test_member_cannot_target_another_user(api_client: TestClient) -> None:
    with _authenticated(UserRole.MEMBER):
        res = api_client.post(
            DELIVERIES_PREFIX, json=_enqueue_payload(recipient_user_id=str(OTHER_USER_ID))
        )
    assert res.status_code == 403, res.text
    assert res.json()["error"]["code"] == "delivery.recipient_not_allowed"
    assert _FakeDeliveryService.calls == []


def test_organization_scope_is_server_derived(api_client: TestClient) -> None:
    """A foreign organization id in the body cannot redirect the row: the
    delivery's organization always comes from the authenticated caller, and
    the recipient is locked to the caller."""
    with _authenticated(UserRole.MEMBER):
        res = api_client.post(
            DELIVERIES_PREFIX,
            json=_enqueue_payload(organization_id=str(uuid.uuid4())),
        )
    assert res.status_code == 201, res.text
    (call,) = _FakeDeliveryService.calls
    assert call[1]["organization_id"] == str(ORG_ID)
    assert call[1]["recipient_user_id"] == str(USER_ID)


# -- action_url validation --------------------------------------------------


@pytest.mark.parametrize(
    "action_url",
    [
        "https://attacker.example/phish",
        "http://attacker.example",
        "javascript:alert(1)",
        "//attacker.example/phish",
        "/\\attacker.example",
        "/%2F%2Fattacker.example",
        "/inbox\n",
        "/inbox zero",
        "inbox",
    ],
)
def test_unsafe_action_url_is_rejected(api_client: TestClient, action_url: str) -> None:
    with _authenticated(UserRole.MEMBER):
        res = api_client.post(
            DELIVERIES_PREFIX, json=_enqueue_payload(action_url=action_url)
        )
    assert res.status_code == 422, res.text
    assert res.json()["error"]["code"] == "delivery.unsafe_action_url"
    assert _FakeDeliveryService.calls == []


# -- allowed path ------------------------------------------------------------


def test_member_can_enqueue_for_self_with_relative_url(api_client: TestClient) -> None:
    with _authenticated(UserRole.MEMBER):
        res = api_client.post(DELIVERIES_PREFIX, json=_enqueue_payload())
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["recipient_user_id"] == str(USER_ID)
    assert body["action_url"] == "/leads/1"
    (call,) = _FakeDeliveryService.calls
    assert call[1]["organization_id"] == str(ORG_ID)
    assert call[1]["channel"] == "email"


def test_omitted_recipient_is_accepted(api_client: TestClient) -> None:
    with _authenticated(UserRole.MEMBER):
        res = api_client.post(
            DELIVERIES_PREFIX, json=_enqueue_payload(recipient_user_id=None)
        )
    assert res.status_code == 201, res.text
    (call,) = _FakeDeliveryService.calls
    assert call[1]["recipient_user_id"] is None
