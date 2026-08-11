"""Unit tests for DeliveryService: enqueue, cancel, retry, statistics (M6)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.errors import AppError
from app.models.delivery import Delivery
from app.models.enums import DeliveryChannel, DeliveryEventType, DeliveryStatus
from app.services.delivery_service import DeliveryService

ORG_ID = uuid.uuid4()
DELIVERY_ID = uuid.uuid4()


class _FakeSessionCM:
    def __init__(self, session) -> None:
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *args) -> None:
        pass


def _delivery(**overrides) -> Delivery:
    defaults = dict(
        organization_id=ORG_ID,
        channel=DeliveryChannel.DASHBOARD,
        subject="subject",
        body="body",
        status=DeliveryStatus.QUEUED,
        attempts=0,
        max_attempts=4,
        payload={},
        provider_metadata={},
    )
    defaults.update(overrides)
    return Delivery(**defaults)


def _patch_delivery_service(
    monkeypatch,
    *,
    existing: Delivery | None = None,
    count_pending: int = 0,
    pending_cap: int = 100,
    commit_error: Exception | None = None,
    provider_available: bool = True,
) -> MagicMock:
    session = MagicMock()
    session.commit = AsyncMock(side_effect=commit_error)
    session.rollback = AsyncMock()

    repo = MagicMock()
    repo.get_by_idempotency = AsyncMock(return_value=existing)
    repo.count_pending = AsyncMock(return_value=count_pending)
    repo.mark_cancelled = AsyncMock(return_value=_delivery(status=DeliveryStatus.CANCELLED))
    repo.mark_cancel_requested = AsyncMock(return_value=_delivery(status=DeliveryStatus.PROCESSING))
    repo.mark_requeued = AsyncMock(return_value=_delivery(status=DeliveryStatus.QUEUED))
    repo.add = MagicMock()

    events_repo = MagicMock()
    events_repo.add = MagicMock()

    class _FakeDeliveryRepo:
        def __init__(self, s) -> None:
            pass

    class _FakeEventRepo:
        def __init__(self, s) -> None:
            pass

    _FakeDeliveryRepo.get_by_idempotency = repo.get_by_idempotency
    _FakeDeliveryRepo.count_pending = repo.count_pending
    _FakeDeliveryRepo.mark_cancelled = repo.mark_cancelled
    _FakeDeliveryRepo.mark_cancel_requested = repo.mark_cancel_requested
    _FakeDeliveryRepo.mark_requeued = repo.mark_requeued
    _FakeDeliveryRepo.add = repo.add
    _FakeDeliveryRepo.get = AsyncMock(return_value=None)
    _FakeDeliveryRepo.count_by_status = AsyncMock(
        return_value={
            "queued": 1,
            "processing": 2,
            "retrying": 3,
            "delivered": 4,
            "failed": 0,
            "cancelled": 0,
        }
    )
    _FakeEventRepo.add = events_repo.add

    monkeypatch.setattr("app.services.delivery_service.DeliveryRepository", _FakeDeliveryRepo)
    monkeypatch.setattr("app.services.delivery_service.DeliveryEventRepository", _FakeEventRepo)
    monkeypatch.setattr(
        "app.services.delivery_service.settings",
        MagicMock(
            DELIVERY_MAX_PENDING_PER_ORG=pending_cap,
            DELIVERY_MAX_ATTEMPTS=4,
            DELIVERY_MAX_PAYLOAD_BYTES=65536,
        ),
    )
    monkeypatch.setattr(
        "app.communication.providers.provider_available", MagicMock(return_value=provider_available)
    )
    session._deliveries = _FakeDeliveryRepo
    session._events = _FakeEventRepo
    return session


def _svc(session) -> DeliveryService:
    return DeliveryService(session)


def test_enqueue_fails_closed_for_unshipped_channel(monkeypatch) -> None:
    session = _patch_delivery_service(monkeypatch, provider_available=False)

    async def run() -> None:
        with pytest.raises(AppError) as exc:
            await _svc(session).enqueue(
                ORG_ID, channel=DeliveryChannel.EMAIL, subject="s", body="b"
            )
        assert exc.value.status_code == 422
        assert exc.value.code == "provider.not_configured"

    import asyncio

    asyncio.run(run())
    session.commit.assert_not_awaited()


def test_enqueue_rejects_oversized_payload(monkeypatch) -> None:
    session = _patch_delivery_service(monkeypatch)
    big = {"data": "x" * 100_000}

    async def run() -> None:
        with pytest.raises(AppError) as exc:
            await _svc(session).enqueue(
                ORG_ID, channel=DeliveryChannel.DASHBOARD, subject="s", body="b", payload=big
            )
        assert exc.value.status_code == 422
        assert exc.value.code == "delivery.payload_too_large"

    import asyncio

    asyncio.run(run())
    session.commit.assert_not_awaited()


def test_enqueue_returns_existing_for_idempotency_key(monkeypatch) -> None:
    existing = _delivery(idempotency_key="key-1")
    session = _patch_delivery_service(monkeypatch, existing=existing)

    async def run() -> None:
        result = await _svc(session).enqueue(
            ORG_ID,
            channel=DeliveryChannel.DASHBOARD,
            subject="s",
            body="b",
            idempotency_key="key-1",
        )
        assert result is existing

    import asyncio

    asyncio.run(run())
    session.commit.assert_not_awaited()


def test_enqueue_rejects_duplicate_via_db_index(monkeypatch) -> None:
    session = _patch_delivery_service(
        monkeypatch, commit_error=IntegrityError("stmt", {}, Exception("dup"))
    )

    async def run() -> None:
        with pytest.raises(AppError) as exc:
            await _svc(session).enqueue(
                ORG_ID,
                channel=DeliveryChannel.DASHBOARD,
                subject="s",
                body="b",
                idempotency_key="key-1",
            )
        assert exc.value.status_code == 409
        assert exc.value.code == "delivery.duplicate_idempotency_key"

    import asyncio

    asyncio.run(run())
    session.rollback.assert_awaited_once()


def test_enqueue_enforces_pending_cap(monkeypatch) -> None:
    session = _patch_delivery_service(monkeypatch, count_pending=100, pending_cap=100)

    async def run() -> None:
        with pytest.raises(AppError) as exc:
            await _svc(session).enqueue(
                ORG_ID, channel=DeliveryChannel.DASHBOARD, subject="s", body="b"
            )
        assert exc.value.status_code == 429
        assert exc.value.code == "delivery.pending_cap_exceeded"

    import asyncio

    asyncio.run(run())
    session.commit.assert_not_awaited()


def test_enqueue_success_creates_queued_delivery(monkeypatch) -> None:
    session = _patch_delivery_service(monkeypatch)
    created: list[object] = []
    session._deliveries.add = lambda _self, d: created.append(d)
    session._events.add = lambda _self, e: created.append(e)

    async def run() -> None:
        delivery = await _svc(session).enqueue(
            ORG_ID,
            channel=DeliveryChannel.DASHBOARD,
            recipient_user_id=uuid.uuid4(),
            subject="subject",
            body="body",
            action_url="/a",
            payload={"k": "v"},
            max_attempts=4,
            idempotency_key="key-1",
        )
        assert delivery.status == DeliveryStatus.QUEUED
        assert delivery.attempts == 0
        assert delivery.max_attempts == 4
        assert delivery.payload == {"k": "v"}

    import asyncio

    asyncio.run(run())
    assert session.commit.await_count == 1
    events = [o for o in created if hasattr(o, "event_type")]
    assert any(e.event_type == DeliveryEventType.QUEUED for e in events)


def test_cancel_immediate_for_queued(monkeypatch) -> None:
    session = _patch_delivery_service(monkeypatch)
    session._deliveries.get = AsyncMock(return_value=_delivery(status=DeliveryStatus.QUEUED))

    async def run() -> None:
        result = await _svc(session).cancel(ORG_ID, DELIVERY_ID, cancelled_by_user_id=uuid.uuid4())
        assert result.status == DeliveryStatus.CANCELLED

    import asyncio

    asyncio.run(run())
    session.commit.assert_awaited_once()


def test_cancel_cooperative_for_processing(monkeypatch) -> None:
    session = _patch_delivery_service(monkeypatch)
    session._deliveries.get = AsyncMock(return_value=_delivery(status=DeliveryStatus.PROCESSING))

    async def run() -> None:
        result = await _svc(session).cancel(ORG_ID, DELIVERY_ID, cancelled_by_user_id=uuid.uuid4())
        assert result.status == DeliveryStatus.PROCESSING

    import asyncio

    asyncio.run(run())
    session._deliveries.mark_cancel_requested.assert_awaited_once()
    session.commit.assert_awaited_once()


def test_cancel_invalid_state(monkeypatch) -> None:
    session = _patch_delivery_service(monkeypatch)
    session._deliveries.get = AsyncMock(return_value=_delivery(status=DeliveryStatus.DELIVERED))

    async def run() -> None:
        with pytest.raises(AppError) as exc:
            await _svc(session).cancel(ORG_ID, DELIVERY_ID)
        assert exc.value.status_code == 409
        assert exc.value.code == "delivery.invalid_state"

    import asyncio

    asyncio.run(run())
    session.commit.assert_not_awaited()


def test_retry_requeues_failed(monkeypatch) -> None:
    session = _patch_delivery_service(monkeypatch)
    session._deliveries.get = AsyncMock(return_value=_delivery(status=DeliveryStatus.FAILED))

    async def run() -> None:
        result = await _svc(session).retry(ORG_ID, DELIVERY_ID)
        assert result.status == DeliveryStatus.QUEUED

    import asyncio

    asyncio.run(run())
    session._deliveries.mark_requeued.assert_awaited_once()
    session.commit.assert_awaited_once()


def test_retry_invalid_state(monkeypatch) -> None:
    session = _patch_delivery_service(monkeypatch)
    session._deliveries.get = AsyncMock(return_value=_delivery(status=DeliveryStatus.QUEUED))

    async def run() -> None:
        with pytest.raises(AppError) as exc:
            await _svc(session).retry(ORG_ID, DELIVERY_ID)
        assert exc.value.code == "delivery.invalid_state"

    import asyncio

    asyncio.run(run())


def test_statistics_include_retrying_and_utilization(monkeypatch) -> None:
    session = _patch_delivery_service(monkeypatch, pending_cap=100)
    result_values = [
        (DeliveryStatus.QUEUED, 1),
        (DeliveryStatus.PROCESSING, 1),
        (DeliveryStatus.RETRYING, 1),
        (DeliveryStatus.DELIVERED, 5),
        (DeliveryStatus.FAILED, 1),
        (DeliveryStatus.CANCELLED, 1),
    ]
    session.execute = AsyncMock(return_value=_Result(result_values))

    async def run() -> None:
        stats = await _svc(session).statistics(ORG_ID)
        assert stats["queued"] == 1
        assert stats["processing"] == 1
        assert stats["retrying"] == 1
        assert stats["delivered"] == 5
        assert stats["pending_cap_utilization_pct"] == 3.0

    import asyncio

    asyncio.run(run())


def test_platform_statistics_has_active_and_terminal(monkeypatch) -> None:
    session = _patch_delivery_service(monkeypatch)

    async def run() -> None:
        stats = await _svc(session).platform_statistics()
        assert stats == {
            "queued": 1,
            "processing": 2,
            "retrying": 3,
            "delivered": 4,
            "failed": 0,
            "cancelled": 0,
            "active": 6,
            "terminal": 4,
        }

    import asyncio

    asyncio.run(run())


class _Scalars:
    def __init__(self, values: list) -> None:
        self._values = values

    def all(self) -> list:
        return self._values


class _Result:
    def __init__(self, values: list) -> None:
        self._values = values

    def all(self) -> list:
        return self._values

    def scalars(self):
        return _Scalars([v for _, v in self._values])
