"""Conversation sender/provenance contract regression tests.

Founder-approved contract (2026-11-11):

* an ordinary authenticated client can create *AGENT* messages only, always
  attributable to itself (``sender_user_id`` is the authenticated user
  regardless of any sender identity fields in the payload);
* ``LEAD`` messages are persisted exclusively through the trusted inbound
  path (``ConversationService.record_inbound_lead_message``), which ordinary
  HTTP clients cannot reach;
* ``SYSTEM`` messages cannot be created by ordinary clients, and no ordinary
  client can spoof sender identity;
* a trusted inbound LEAD message reopens a closed conversation
  (founder-approved), in the same transaction as the message insert;
* duplicate provider deliveries (same external_id) are idempotent;
* a failed message insert never reopens the conversation;
* timestamps are server-authoritative, with provider timestamps accepted
  only when explicitly timezone-aware.

Smoke-level authorization wiring (LEAD_READ reads, LEAD_WRITE mutations) is
enforced by the endpoint's ``require_permission`` dependencies and the RBAC
matrix; both are exercised by the API/permission suites.

Note on SYSTEM: the codebase contains no SYSTEM message ingress (nothing in
the service, endpoint or agent paths creates one). The only guarantee this
module can give today is that ordinary clients cannot create one — covered
by the sender rejection tests. A SYSTEM ingress, if ever built, must live on
a trusted internal path like the LEAD ingress.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.permissions import Permission, has_permission
from app.models.conversation import Conversation
from app.models.conversation_message import ConversationMessage
from app.models.enums import ConversationSender, OutreachChannel, UserRole
from app.models.user import User
from app.services.base import utcnow
from app.services.conversation_service import ConversationService

ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
LEAD_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
CONVERSATION_ID = uuid.UUID("00000000-0000-0000-0000-000000000003")


class FakeSession:
    """Minimal async session: records adds; flush/commit/rollback are no-ops."""

    def __init__(self) -> None:
        self.added: list[object] = []
        self.committed = False
        self.rolled_back = False

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True

    async def refresh(self, instance: object) -> None:
        return None

    async def execute(self, *args: object, **kwargs: object) -> None:
        return None


def _closed_conversation() -> Conversation:
    conv = Conversation(
        organization_id=ORG_ID,
        lead_id=LEAD_ID,
        channel=OutreachChannel.EMAIL,
        subject="Hello",
        is_open=False,
    )
    conv.id = CONVERSATION_ID
    conv.last_message_at = None
    return conv


def _make_user(role: UserRole = UserRole.OWNER) -> User:
    user = User(
        organization_id=ORG_ID,
        email="owner@example.com",
        full_name="Owner",
        role=role,
        password_hash=None,
    )
    user.id = uuid.uuid4()
    user.created_at = utcnow()
    user.updated_at = utcnow()
    user.is_active = True
    return user


def _service(conv: Conversation | None = None) -> tuple[ConversationService, FakeSession]:
    session = FakeSession()
    service = ConversationService(session)  # type: ignore[arg-type]
    service._conversations = MagicMock()
    service._messages = MagicMock()
    if conv is not None:
        service._conversations.get_or_404 = AsyncMock(return_value=conv)
    service._messages.add = MagicMock()
    service._messages.get_by_external_id = AsyncMock(return_value=None)
    return service, session


# -- Ordinary path (add_message): AGENT attribution and sender rejection --


@pytest.mark.asyncio
async def test_ordinary_path_rejects_lead_sender() -> None:
    conv = _closed_conversation()
    service, session = _service(conv)

    with pytest.raises(AppError) as exc_info:
        await service.add_message(
            ORG_ID, conv.id, {"sender_type": "lead", "body": "lead here"}, actor=_make_user()
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "conversation.sender_not_allowed"
    assert session.committed is False


@pytest.mark.asyncio
async def test_ordinary_path_rejects_system_sender() -> None:
    conv = _closed_conversation()
    service, session = _service(conv)

    with pytest.raises(AppError) as exc_info:
        await service.add_message(
            ORG_ID, conv.id, {"sender_type": "system", "body": "system event"}, actor=_make_user()
        )

    assert exc_info.value.status_code == 403
    assert session.committed is False


@pytest.mark.asyncio
async def test_ordinary_path_ignores_payload_sender_user_id() -> None:
    conv = _closed_conversation()
    service, session = _service(conv)
    actor = _make_user()
    spoofed = uuid.uuid4()

    message = await service.add_message(
        ORG_ID,
        conv.id,
        {"sender_type": "agent", "body": "Following up", "sender_user_id": spoofed},
        actor=actor,
    )

    assert message.sender_user_id == actor.id
    assert message.sender_user_id != spoofed


# -- Trusted inbound path: LEAD only, provenance forced --


@pytest.mark.asyncio
async def test_inbound_path_rejects_agent_claim() -> None:
    conv = _closed_conversation()
    service, session = _service(conv)

    with pytest.raises(AppError) as exc_info:
        await service.record_inbound_lead_message(
            ORG_ID, conv.id, {"sender_type": "agent", "body": "fake agent"}
        )

    assert exc_info.value.status_code == 403
    assert session.committed is False


@pytest.mark.asyncio
async def test_inbound_path_rejects_system_claim() -> None:
    conv = _closed_conversation()
    service, session = _service(conv)

    with pytest.raises(AppError) as exc_info:
        await service.record_inbound_lead_message(
            ORG_ID, conv.id, {"sender_type": "system", "body": "fake system"}
        )

    assert exc_info.value.status_code == 403
    assert session.committed is False


@pytest.mark.asyncio
async def test_inbound_path_rejects_unknown_sender() -> None:
    conv = _closed_conversation()
    service, session = _service(conv)

    with pytest.raises(AppError) as exc_info:
        await service.record_inbound_lead_message(
            ORG_ID, conv.id, {"sender_type": "bot", "body": "hello"}
        )

    assert exc_info.value.status_code == 422
    assert session.committed is False


@pytest.mark.asyncio
async def test_inbound_lead_message_reopens_and_uses_provider_timestamp() -> None:
    conv = _closed_conversation()
    service, session = _service(conv)
    provider_ts = "2026-11-01T10:00:00+00:00"

    message = await service.record_inbound_lead_message(
        ORG_ID, conv.id, {"body": "Yes, let's talk!", "sent_at": provider_ts}
    )

    assert message.sender_type is ConversationSender.LEAD
    assert message.sender_user_id is None
    assert message.sent_at == datetime(2026, 11, 1, 10, 0, tzinfo=UTC)
    assert conv.is_open is True
    assert conv.last_message_at == datetime(2026, 11, 1, 10, 0, tzinfo=UTC)
    assert session.committed is True


@pytest.mark.asyncio
async def test_inbound_lead_message_without_provider_timestamp_uses_server_clock() -> None:
    conv = _closed_conversation()
    service, session = _service(conv)
    before = utcnow()

    message = await service.record_inbound_lead_message(ORG_ID, conv.id, {"body": "Hi"})

    assert message.sent_at >= before
    assert message.sent_at.tzinfo is not None
    assert conv.is_open is True


@pytest.mark.asyncio
async def test_inbound_lead_message_naive_timestamp_rejected() -> None:
    conv = _closed_conversation()
    service, session = _service(conv)

    with pytest.raises(AppError) as exc_info:
        await service.record_inbound_lead_message(
            ORG_ID, conv.id, {"body": "Hi", "sent_at": "2026-11-01T10:00:00"}
        )

    assert exc_info.value.code == "conversation.naive_timestamp"
    assert exc_info.value.status_code == 422
    assert session.committed is False


@pytest.mark.asyncio
async def test_inbound_lead_message_duplicate_external_id_is_idempotent() -> None:
    conv = _closed_conversation()
    service, session = _service(conv)
    existing = ConversationMessage(
        conversation_id=conv.id,
        organization_id=ORG_ID,
        sender_type=ConversationSender.LEAD,
        sender_user_id=None,
        body="Yes, let's talk!",
        external_id="provider-message-1",
        metadata_={},
        sent_at=utcnow(),
    )
    service._messages.get_by_external_id = AsyncMock(return_value=existing)

    message = await service.record_inbound_lead_message(
        ORG_ID, conv.id, {"body": "Yes, let's talk!", "external_id": "provider-message-1"}
    )

    assert message is existing
    service._messages.add.assert_not_called()
    assert conv.is_open is False
    assert conv.last_message_at is None
    assert session.committed is False


@pytest.mark.asyncio
async def test_inbound_lead_message_unknown_conversation_raises() -> None:
    service, session = _service(None)
    service._conversations.get_or_404 = AsyncMock(
        side_effect=AppError(
            code="conversation.not_found",
            message="Conversation not found",
            status_code=404,
        )
    )

    with pytest.raises(AppError) as exc_info:
        await service.record_inbound_lead_message(ORG_ID, CONVERSATION_ID, {"body": "Hi"})

    assert exc_info.value.status_code == 404
    service._messages.add.assert_not_called()
    assert session.committed is False


@pytest.mark.asyncio
async def test_cross_tenant_lead_reference_is_rejected() -> None:
    session = FakeSession()
    service = ConversationService(session)  # type: ignore[arg-type]

    class _LeadRepo:
        def __init__(self, s: AsyncSession) -> None:
            pass

        async def get(self, organization_id: uuid.UUID, lead_id: uuid.UUID):
            return None  # RLS / org scoping hides foreign-tenant leads

    import app.services.conversation_service as service_module

    original = service_module.LeadRepository
    service_module.LeadRepository = _LeadRepo  # type: ignore[assignment]
    try:
        with pytest.raises(AppError) as exc_info:
            await service.create(
                ORG_ID,
                {
                    "lead_id": LEAD_ID,
                    "channel": OutreachChannel.EMAIL.value,
                    "subject": "x",
                },
            )
    finally:
        service_module.LeadRepository = original  # type: ignore[assignment]

    assert exc_info.value.status_code == 404
    assert session.added == []


@pytest.mark.asyncio
async def test_inbound_lead_message_failed_insert_does_not_reopen() -> None:
    conv = _closed_conversation()
    service, session = _service(conv)
    service._messages.add = MagicMock(side_effect=RuntimeError("db write failed"))

    with pytest.raises(RuntimeError):
        await service.record_inbound_lead_message(ORG_ID, conv.id, {"body": "Hi"})

    assert conv.is_open is False
    assert session.committed is False


@pytest.mark.asyncio
async def test_inbound_lead_message_failed_commit_does_not_reopen() -> None:
    conv = _closed_conversation()
    service, session = _service(conv)

    from app.services import conversation_service as service_module

    original = service_module.commit_with_retry

    async def _failing_commit(session: object) -> None:
        await session.rollback()  # type: ignore[attr-defined]
        raise RuntimeError("commit failed and the transaction was rolled back")

    service_module.commit_with_retry = _failing_commit  # type: ignore[assignment]
    try:
        with pytest.raises(RuntimeError):
            await service.record_inbound_lead_message(ORG_ID, conv.id, {"body": "Hi"})
    finally:
        service_module.commit_with_retry = original  # type: ignore[assignment]

    # The exception propagates and the session rollback() was invoked inside
    # the failing commit, so no message and no reopen is durable. Verified
    # against a fake session only; PostgreSQL rollback semantics are
    # exercised by tests/integration (not runnable in this environment).
    assert session.committed is False
    assert session.rolled_back is True


# -- Authorization contract: VIEWER reads but cannot mutate --


def test_viewer_cannot_mutate_conversations() -> None:
    assert has_permission(UserRole.VIEWER, Permission.LEAD_READ) is True
    assert has_permission(UserRole.VIEWER, Permission.LEAD_WRITE) is False
    # The conversation endpoints require exactly these permissions.
    assert has_permission(UserRole.SALES_AGENT, Permission.LEAD_WRITE) is True
    assert has_permission(UserRole.MEMBER, Permission.LEAD_WRITE) is True


# -- Invalid sender/actor values: deterministic domain errors, never 500 -----


@pytest.mark.asyncio
async def test_add_message_unknown_sender_is_domain_error_not_valueerror() -> None:
    """An unknown sender_type through the ordinary path is a typed 422, not a
    bare ``ValueError`` that would surface as HTTP 500."""
    conv = _closed_conversation()
    service, session = _service(conv)

    with pytest.raises(AppError) as exc_info:
        await service.add_message(
            ORG_ID, conv.id, {"sender_type": "robot", "body": "hi"}, actor=_make_user()
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "conversation.invalid_sender"
    assert session.committed is False
    service._messages.add.assert_not_called()


@pytest.mark.asyncio
async def test_add_message_missing_actor_is_rejected() -> None:
    """Agent attribution is mandatory: a caller without an attributable actor
    gets a deterministic validation error and nothing is persisted."""
    conv = _closed_conversation()
    service, session = _service(conv)

    with pytest.raises(AppError) as exc_info:
        await service.add_message(
            ORG_ID, conv.id, {"sender_type": "agent", "body": "hi"}, actor=None
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "conversation.actor_required"
    assert session.committed is False
    service._messages.add.assert_not_called()
