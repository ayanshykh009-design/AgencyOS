"""API-level RBAC and sender-contract tests for the conversations router.

Proves at the HTTP boundary:

* reads require ``LEAD_READ`` (VIEWER keeps read access),
* mutations require ``LEAD_WRITE`` (VIEWER is forbidden and never reaches the
  service layer),
* the ordinary message endpoint is driven with the caller's identity as the
  server-authoritative ``actor`` (payload ``sender_user_id`` cannot override
  it),
* an unknown ``sender_type`` is rejected with 422 by request validation before
  the handler runs (no unhandled ``ValueError``/500),
* the trusted inbound LEAD path (``ConversationService.record_inbound_lead_message``)
  has no HTTP entry point — structural guard over every router module.

Sender provenance (LEAD/SYSTEM rejection by the service, trusted inbound
semantics) is proven at service level in ``tests/unit/test_conversation_contract.py``.
"""

from __future__ import annotations

import ast
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_db
from app.core.permissions import Permission, has_permission
from app.main import app
from app.models.enums import ConversationSender, UserRole

ORG_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
OTHER_USER_ID = uuid.uuid4()
LEAD_ID = uuid.uuid4()
CONVERSATION_ID = uuid.uuid4()
MESSAGE_ID = uuid.uuid4()
CONVERSATIONS_PREFIX = "/api/v1/conversations"


class _FakeConversationService:
    """Records service calls; returns API-shaped rows for the success path."""

    calls: list[tuple[str, dict[str, Any]]] = []

    def __init__(self, session: Any) -> None:
        self._session = session

    async def list_open(
        self, organization_id: uuid.UUID, *, limit: int = 100, offset: int = 0
    ) -> list[Any]:
        self.calls.append(("list_open", {"organization_id": str(organization_id)}))
        return []

    async def add_message(
        self,
        organization_id: uuid.UUID,
        conversation_id: uuid.UUID,
        data: dict[str, Any],
        *,
        actor: Any,
    ) -> Any:
        self.calls.append(
            (
                "add_message",
                {
                    "organization_id": str(organization_id),
                    "conversation_id": str(conversation_id),
                    "actor_id": str(actor.id),
                    "sender_type": data.get("sender_type"),
                    "requested_sender_user_id": data.get("sender_user_id"),
                },
            )
        )
        return _message_row(actor.id)


def _message_row(sender_user_id: uuid.UUID) -> Any:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=MESSAGE_ID,
        conversation_id=CONVERSATION_ID,
        organization_id=ORG_ID,
        sender_type=ConversationSender.AGENT,
        sender_user_id=sender_user_id,
        body="Following up",
        external_id=None,
        metadata_={},
        metadata={},
        sent_at=now,
        created_at=now,
    )


@pytest.fixture
def conv_service(monkeypatch: pytest.MonkeyPatch) -> type[_FakeConversationService]:
    """Patch the endpoint module's service class with a call-recording fake."""
    _FakeConversationService.calls = []
    monkeypatch.setattr(
        "app.api.v1.endpoints.conversations.ConversationService", _FakeConversationService
    )
    return _FakeConversationService


@pytest.fixture
def api_client(conv_service: type[_FakeConversationService]) -> Generator[TestClient, None, None]:
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


def _message_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "conversation_id": str(CONVERSATION_ID),
        "organization_id": str(ORG_ID),
        "sender_type": "agent",
        "body": "Following up",
    }
    payload.update(overrides)
    return payload


# -- policy / matrix --------------------------------------------------------


def test_conversation_permission_matrix() -> None:
    assert has_permission(UserRole.VIEWER, Permission.LEAD_READ)
    assert not has_permission(UserRole.VIEWER, Permission.LEAD_WRITE)
    for role in (
        UserRole.OWNER,
        UserRole.ADMIN,
        UserRole.MANAGER,
        UserRole.MEMBER,
        UserRole.SALES_AGENT,
    ):
        assert has_permission(role, Permission.LEAD_WRITE)


# -- rejection paths --------------------------------------------------------


def test_unauthenticated_message_write_is_rejected(api_client: TestClient) -> None:
    res = api_client.post(
        f"{CONVERSATIONS_PREFIX}/{CONVERSATION_ID}/messages", json=_message_payload()
    )
    assert res.status_code == 401, res.text
    assert _FakeConversationService.calls == []


def test_viewer_write_is_forbidden_and_never_reaches_the_service(api_client: TestClient) -> None:
    with _authenticated(UserRole.VIEWER):
        res = api_client.post(
            f"{CONVERSATIONS_PREFIX}/{CONVERSATION_ID}/messages", json=_message_payload()
        )
    assert res.status_code == 403, res.text
    assert _FakeConversationService.calls == []


def test_unknown_sender_is_rejected_with_422_before_the_handler(api_client: TestClient) -> None:
    """An invalid ``sender_type`` cannot blow up as a 500: the request schema
    (a ``ConversationSender`` enum) rejects it during validation."""
    with _authenticated(UserRole.OWNER):
        res = api_client.post(
            f"{CONVERSATIONS_PREFIX}/{CONVERSATION_ID}/messages",
            json=_message_payload(sender_type="robot"),
        )
    assert res.status_code == 422, res.text
    assert _FakeConversationService.calls == []


# -- allowed paths ----------------------------------------------------------


def test_viewer_keeps_read_access(api_client: TestClient) -> None:
    with _authenticated(UserRole.VIEWER):
        res = api_client.get(f"{CONVERSATIONS_PREFIX}/open")
    assert res.status_code == 200, res.text
    assert res.json() == []


def test_agent_message_is_attributed_to_the_caller(api_client: TestClient) -> None:
    with _authenticated(UserRole.MEMBER):
        res = api_client.post(
            f"{CONVERSATIONS_PREFIX}/{CONVERSATION_ID}/messages", json=_message_payload()
        )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["sender_type"] == "agent"
    assert body["sender_user_id"] == str(USER_ID)
    (call,) = _FakeConversationService.calls
    assert call[0] == "add_message"
    assert call[1]["actor_id"] == str(USER_ID)
    assert call[1]["organization_id"] == str(ORG_ID)


def test_payload_sender_user_id_cannot_override_the_actor(api_client: TestClient) -> None:
    """A client-supplied ``sender_user_id`` is ignored: the actor is the
    authenticated user (server-authoritative attribution)."""
    with _authenticated(UserRole.MEMBER):
        res = api_client.post(
            f"{CONVERSATIONS_PREFIX}/{CONVERSATION_ID}/messages",
            json=_message_payload(sender_user_id=str(OTHER_USER_ID)),
        )
    assert res.status_code == 201, res.text
    (call,) = _FakeConversationService.calls
    assert call[1]["actor_id"] == str(USER_ID)
    assert res.json()["sender_user_id"] == str(USER_ID)


# -- structural guard: no HTTP entry point for the trusted inbound path ------


def test_no_router_references_the_trusted_inbound_path() -> None:
    """``record_inbound_lead_message`` must never be reachable from an HTTP
    router: LEAD messages may only be persisted by trusted internal callers
    (e.g. a future authenticated provider-ingress worker)."""
    app_dir = Path(__file__).resolve().parents[2] / "app" / "api"
    offenders: list[str] = []
    for path in app_dir.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == "record_inbound_lead_message":
                offenders.append(f"{path.relative_to(app_dir)}:{node.lineno}")
            elif isinstance(node, ast.Attribute) and node.attr == "record_inbound_lead_message":
                offenders.append(f"{path.relative_to(app_dir)}:{node.lineno}")
    assert offenders == [], f"trusted inbound path reachable from routers: {offenders}"
