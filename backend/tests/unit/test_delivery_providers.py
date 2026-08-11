"""Unit tests for the M6 provider contract + shipped providers."""
from __future__ import annotations

import uuid

import pytest

from app.communication.contract import (
    DeliveryError,
    DeliveryMessage,
    DeliveryProvider,
    DeliveryResult,
    PermanentDeliveryError,
    RetryableDeliveryError,
)
from app.communication.inapp_provider import InAppProvider
from app.communication.providers import (
    DeliveryProviderRegistry,
    DeliveryProviderUnavailable,
    get_provider,
    provider_available,
    sanitize_error,
)
from app.communication.test_doubles import (
    CrashedProvider,
    FailureProvider,
    PermanentFailureProvider,
    StubProvider,
    TimeoutProvider,
)
from app.models.enums import DeliveryChannel, NotificationType


def _message(**overrides) -> DeliveryMessage:
    defaults = dict(
        delivery_id=uuid.uuid4(),
        idempotency_key=None,
        organization_id=uuid.uuid4(),
        recipient_user_id=uuid.uuid4(),
        subject="subject",
        body="body",
        action_url=None,
        metadata={},
    )
    defaults.update(overrides)
    return DeliveryMessage(**defaults)


# -- error hierarchy -------------------------------------------------


def test_error_hierarchy() -> None:
    base = DeliveryError("provider.bad", "boom")
    assert base.code == "provider.bad"
    assert isinstance(RetryableDeliveryError("provider.unavailable", "x"), DeliveryError)
    assert isinstance(PermanentDeliveryError("provider.not_configured", "x"), DeliveryError)
    assert not isinstance(RetryableDeliveryError("x", "y"), PermanentDeliveryError)


def test_delivery_result_fields() -> None:
    ok = DeliveryResult(ok=True, provider_metadata={"a": 1})
    assert ok.ok and ok.provider_metadata == {"a": 1} and ok.error is None


# -- registry --------------------------------------------------------


def test_dashboard_provider_registered_only() -> None:
    assert provider_available(DeliveryChannel.DASHBOARD)
    assert not provider_available(DeliveryChannel.EMAIL)
    assert not provider_available(DeliveryChannel.WHATSAPP)
    assert not provider_available(DeliveryChannel.PUSH)


def test_get_provider_unavailable_raises() -> None:
    with pytest.raises(DeliveryProviderUnavailable):
        get_provider(DeliveryChannel.EMAIL, session=None)  # type: ignore[arg-type]


def test_get_provider_returns_session_bound_instance() -> None:
    session = object()
    provider = get_provider(DeliveryChannel.DASHBOARD, session)  # type: ignore[arg-type]
    assert isinstance(provider, InAppProvider)
    assert provider._session is session


def test_registry_registered_class_is_inapp() -> None:
    assert DeliveryProviderRegistry._providers[DeliveryChannel.DASHBOARD] is InAppProvider


def test_sanitize_error_short_and_safe() -> None:
    assert sanitize_error(ValueError(" ")) == "ValueError"
    long_msg = "x" * 2000
    assert len(sanitize_error(RuntimeError(long_msg))) == 500


# -- InAppProvider ---------------------------------------------------


class _FakeSession:
    def __init__(self) -> None:
        self.added: list = []
        self.flushed = False

    def add(self, obj) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        self.flushed = True


def test_inapp_provider_creates_notification_and_metadata() -> None:
    session = _FakeSession()
    provider = InAppProvider(session)
    message = _message(action_url="/a", metadata={"key": "value"})

    result = None

    async def run() -> None:
        nonlocal result
        result = await provider.deliver(message)

    import asyncio

    asyncio.run(run())
    assert result.ok is True
    assert len(session.added) == 1
    notification = session.added[0]
    assert notification.organization_id == message.organization_id
    assert notification.user_id == message.recipient_user_id
    assert notification.type == NotificationType.SYSTEM
    assert notification.title == message.subject
    assert notification.body == message.body
    assert notification.action_url == "/a"
    assert notification.metadata_ == {"key": "value", "delivery_id": str(message.delivery_id)}
    assert result.provider_metadata["notification_id"] == str(notification.id)
    assert session.flushed is True


def test_inapp_provider_uses_approval_request_type() -> None:
    session = _FakeSession()
    provider = InAppProvider(session)
    message = _message(metadata={"approval_request_id": str(uuid.uuid4())})

    async def run() -> None:
        await provider.deliver(message)

    import asyncio

    asyncio.run(run())
    assert session.added[0].type == NotificationType.APPROVAL_REQUEST


def test_inapp_provider_respects_notification_type_hint() -> None:
    session = _FakeSession()
    provider = InAppProvider(session)
    message = _message(metadata={"notification_type": "workflow_event"})

    async def run() -> None:
        await provider.deliver(message)

    import asyncio

    asyncio.run(run())
    assert session.added[0].type == NotificationType.WORKFLOW_EVENT


# -- test doubles ----------------------------------------------------


def test_stub_provider_always_succeeds_and_records() -> None:
    provider = StubProvider()
    message = _message()

    async def run() -> None:
        result = await provider.deliver(message)
        assert result.ok is True
        assert result.provider_metadata == {"stub": True}

    import asyncio

    asyncio.run(run())
    assert provider.calls == [message]


def test_failure_provider_raises_retryable() -> None:
    provider = FailureProvider()

    async def run() -> None:
        with pytest.raises(RetryableDeliveryError) as exc:
            await provider.deliver(_message())
        assert exc.value.code == "provider.unavailable"

    import asyncio

    asyncio.run(run())


def test_permanent_failure_provider_raises_permanent() -> None:
    provider = PermanentFailureProvider()

    async def run() -> None:
        with pytest.raises(PermanentDeliveryError) as exc:
            await provider.deliver(_message())
        assert exc.value.code == "provider.not_configured"

    import asyncio

    asyncio.run(run())


def test_timeout_provider_hangs_past_timeout() -> None:
    provider = TimeoutProvider(delay_seconds=60)

    async def run() -> None:
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(provider.deliver(_message()), timeout=0.01)

    import asyncio

    asyncio.run(run())


def test_crashed_provider_raises_unexpected() -> None:
    provider = CrashedProvider()

    async def run() -> None:
        with pytest.raises(RuntimeError):
            await provider.deliver(_message())

    import asyncio

    asyncio.run(run())


def test_test_doubles_are_delivery_providers() -> None:
    for provider in (StubProvider(), FailureProvider(), PermanentFailureProvider()):
        assert isinstance(provider, DeliveryProvider)
