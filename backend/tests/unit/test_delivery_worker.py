"""Unit tests for DeliveryWorker: backoff, dispatch outcomes, recovery (M6)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from app.communication.contract import (
    DeliveryMessage,
    DeliveryResult,
)
from app.communication.test_doubles import StubProvider
from app.models.delivery import Delivery
from app.models.enums import DeliveryChannel, DeliveryEventType, DeliveryStatus
from app.workers.delivery_worker import DeliveryWorker

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
        id=DELIVERY_ID,
        organization_id=ORG_ID,
        channel=DeliveryChannel.DASHBOARD,
        subject="subject",
        body="body",
        status=DeliveryStatus.PROCESSING,
        attempts=1,
        max_attempts=4,
        payload={},
        provider_metadata={},
        cancel_requested_at=None,
        scheduled_for=datetime.now(UTC),
    )
    defaults.update(overrides)
    return Delivery(**defaults)


def _patch_worker(monkeypatch, provider=None) -> tuple[DeliveryWorker, MagicMock, list]:
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()

    deliveries_repo = MagicMock()
    events_repo = MagicMock()
    added_events: list = []
    events_repo.add = lambda e: added_events.append(e)

    session._deliveries = deliveries_repo
    session._events = events_repo

    monkeypatch.setattr(
        "app.workers.delivery_worker.DeliveryRepository", MagicMock(return_value=deliveries_repo)
    )
    monkeypatch.setattr(
        "app.workers.delivery_worker.DeliveryEventRepository", MagicMock(return_value=events_repo)
    )
    monkeypatch.setattr(
        "app.workers.delivery_worker.settings",
        MagicMock(
            DELIVERY_BATCH_SIZE=10,
            DELIVERY_ORGS_PER_SWEEP=20,
            DELIVERY_ACTIVE_TIMEOUT_SECONDS=30,
            DELIVERY_RETRY_BASE_SECONDS=10,
            DELIVERY_RECOVERY_SECONDS=300,
            DELIVERY_STATEMENT_TIMEOUT_SECONDS=30,
            DELIVERY_ENABLED=True,
        ),
    )
    if provider is not None:
        monkeypatch.setattr(
            "app.workers.delivery_worker.get_provider", MagicMock(return_value=provider)
        )

    worker = DeliveryWorker(session_factory=lambda: _FakeSessionCM(session))
    return worker, session, added_events


# -- backoff ---------------------------------------------------------


def test_backoff_sequence() -> None:
    assert DeliveryWorker._backoff(1) == 10
    assert DeliveryWorker._backoff(2) == 20
    assert DeliveryWorker._backoff(3) == 40
    assert DeliveryWorker._backoff(4) == 80


def test_backoff_capped_at_one_hour() -> None:
    assert DeliveryWorker._backoff(20) == 3600


# -- message mapping -------------------------------------------------


def test_to_message_injects_approval_request_id() -> None:
    approval_id = uuid.uuid4()
    delivery = _delivery(
        idempotency_key="key-1",
        action_url="/a",
        payload={"k": "v"},
        approval_request_id=approval_id,
    )
    message = DeliveryWorker._to_message(delivery)
    assert isinstance(message, DeliveryMessage)
    assert message.delivery_id == DELIVERY_ID
    assert message.idempotency_key == "key-1"
    assert message.action_url == "/a"
    assert message.metadata == {"k": "v", "approval_request_id": str(approval_id)}


# -- dispatch outcomes ------------------------------------------------


def test_drain_org_delivered_flow(monkeypatch) -> None:
    worker, session, added_events = _patch_worker(monkeypatch, provider=StubProvider())
    queued = _delivery(status=DeliveryStatus.QUEUED)
    claimed = _delivery(status=DeliveryStatus.PROCESSING, attempts=1)
    session._deliveries.get_queued_for_org = AsyncMock(return_value=[queued])
    session._deliveries.claim = AsyncMock(return_value=claimed)
    session._deliveries.mark_delivered = AsyncMock(
        return_value=_delivery(status=DeliveryStatus.DELIVERED, attempts=1)
    )

    async def run() -> None:
        sent = await worker._drain_org(ORG_ID, session)
        assert sent == 1

    import asyncio

    asyncio.run(run())
    session.commit.assert_awaited_once()
    event_types = [e.event_type for e in added_events]
    assert DeliveryEventType.CLAIMED in event_types
    assert DeliveryEventType.PROVIDER_DISPATCHED in event_types
    assert DeliveryEventType.PROVIDER_RETURNED in event_types
    assert DeliveryEventType.DELIVERED in event_types


def test_attempt_retryable_schedules_retry(monkeypatch) -> None:
    from app.communication.test_doubles import FailureProvider

    worker, session, added_events = _patch_worker(monkeypatch, provider=FailureProvider())
    claimed = _delivery()
    session._deliveries.schedule_retry = AsyncMock(
        return_value=_delivery(status=DeliveryStatus.RETRYING, attempts=1)
    )

    async def run() -> None:
        await worker._attempt(session, ORG_ID, claimed, session._deliveries, session._events)

    import asyncio

    asyncio.run(run())
    session._deliveries.schedule_retry.assert_awaited_once()
    session._deliveries.mark_failed.assert_not_called()
    assert DeliveryEventType.RETRYING in [e.event_type for e in added_events]


def test_attempt_permanent_fails_immediately(monkeypatch) -> None:
    from app.communication.test_doubles import PermanentFailureProvider

    worker, session, _ = _patch_worker(monkeypatch, provider=PermanentFailureProvider())
    claimed = _delivery(attempts=1)
    session._deliveries.mark_failed = AsyncMock(
        return_value=_delivery(status=DeliveryStatus.FAILED, attempts=1)
    )

    async def run() -> None:
        await worker._attempt(session, ORG_ID, claimed, session._deliveries, session._events)

    import asyncio

    asyncio.run(run())
    session._deliveries.mark_failed.assert_awaited_once()
    session._deliveries.schedule_retry.assert_not_called()


def test_attempt_timeout_schedules_retry(monkeypatch) -> None:
    from app.communication.test_doubles import TimeoutProvider

    worker, session, added_events = _patch_worker(
        monkeypatch, provider=TimeoutProvider(delay_seconds=60)
    )
    claimed = _delivery(attempts=1)
    session._deliveries.schedule_retry = AsyncMock(
        return_value=_delivery(status=DeliveryStatus.RETRYING, attempts=1)
    )

    async def run() -> None:
        await worker._attempt(session, ORG_ID, claimed, session._deliveries, session._events)

    import asyncio

    asyncio.run(run())
    session._deliveries.schedule_retry.assert_awaited_once()
    assert DeliveryEventType.RETRYING in [e.event_type for e in added_events]


def test_attempt_ok_false_schedules_retry(monkeypatch) -> None:
    class OkFalseProvider(StubProvider):
        async def deliver(self, message):
            return DeliveryResult(ok=False, error="provider said no")

    worker, session, _ = _patch_worker(monkeypatch, provider=OkFalseProvider())
    claimed = _delivery()
    session._deliveries.schedule_retry = AsyncMock(
        return_value=_delivery(status=DeliveryStatus.RETRYING, attempts=1)
    )

    async def run() -> None:
        await worker._attempt(session, ORG_ID, claimed, session._deliveries, session._events)

    import asyncio

    asyncio.run(run())
    session._deliveries.schedule_retry.assert_awaited_once()


def test_attempt_unexpected_error_is_retryable(monkeypatch) -> None:
    from app.communication.test_doubles import CrashedProvider

    worker, session, _ = _patch_worker(monkeypatch, provider=CrashedProvider())
    claimed = _delivery()
    session._deliveries.schedule_retry = AsyncMock(
        return_value=_delivery(status=DeliveryStatus.RETRYING, attempts=1)
    )

    async def run() -> None:
        await worker._attempt(session, ORG_ID, claimed, session._deliveries, session._events)

    import asyncio

    asyncio.run(run())
    session._deliveries.schedule_retry.assert_awaited_once()


def test_land_exhausted_attempts_fails(monkeypatch) -> None:
    worker, session, added_events = _patch_worker(monkeypatch)
    claimed = _delivery(attempts=4, max_attempts=4)
    session._deliveries.mark_failed = AsyncMock(
        return_value=_delivery(status=DeliveryStatus.FAILED, attempts=4)
    )

    async def run() -> None:
        await worker._land(
            ORG_ID,
            claimed,
            outcome="retry",
            error="boom",
            deliveries_repo=session._deliveries,
            events_repo=session._events,
        )

    import asyncio

    asyncio.run(run())
    session._deliveries.mark_failed.assert_awaited_once()
    session._deliveries.schedule_retry.assert_not_called()
    assert DeliveryEventType.FAILED in [e.event_type for e in added_events]


def test_land_honours_cancel_request(monkeypatch) -> None:
    worker, session, added_events = _patch_worker(monkeypatch)
    claimed = _delivery(cancel_requested_at=datetime.now(UTC), attempts=1)
    session._deliveries.mark_cancelled_after_send = AsyncMock(
        return_value=_delivery(status=DeliveryStatus.CANCELLED, attempts=1)
    )

    async def run() -> None:
        await worker._land(
            ORG_ID,
            claimed,
            outcome="retry",
            error="boom",
            deliveries_repo=session._deliveries,
            events_repo=session._events,
        )

    import asyncio

    asyncio.run(run())
    session._deliveries.mark_cancelled_after_send.assert_awaited_once()
    session._deliveries.schedule_retry.assert_not_called()
    assert DeliveryEventType.CANCELLED in [e.event_type for e in added_events]


def test_land_permanent_failure_ignores_cancel_and_fails(monkeypatch) -> None:
    worker, session, _ = _patch_worker(monkeypatch)
    claimed = _delivery(cancel_requested_at=datetime.now(UTC), attempts=1)
    session._deliveries.mark_failed = AsyncMock(
        return_value=_delivery(status=DeliveryStatus.FAILED, attempts=1)
    )

    async def run() -> None:
        await worker._land(
            ORG_ID,
            claimed,
            outcome="failed",
            error="permanent",
            deliveries_repo=session._deliveries,
            events_repo=session._events,
        )

    import asyncio

    asyncio.run(run())
    session._deliveries.mark_failed.assert_awaited_once()
    session._deliveries.mark_cancelled_after_send.assert_not_called()


# -- recovery ---------------------------------------------------------


def test_recover_stale_stamps_guard_events(monkeypatch) -> None:
    worker, session, added_events = _patch_worker(monkeypatch)
    stale = _delivery(attempts=1, updated_at=datetime.now(UTC) - timedelta(minutes=10))
    session._deliveries.list_stale_processing = AsyncMock(return_value=[stale])
    session._deliveries.requeue_stale = AsyncMock(
        return_value=_delivery(status=DeliveryStatus.QUEUED)
    )

    async def run() -> None:
        recovered = await worker._recover_stale(session)
        assert recovered == 1

    import asyncio

    asyncio.run(run())
    session._deliveries.requeue_stale.assert_awaited_once()
    event_types = [e.event_type for e in added_events]
    assert DeliveryEventType.TIMED_OUT in event_types
    assert DeliveryEventType.RECOVERY_GUARD in event_types


# -- sweep loop -------------------------------------------------------


def test_sweep_once_returns_counters(monkeypatch) -> None:
    worker, session, _ = _patch_worker(monkeypatch, provider=StubProvider())
    stale = _delivery(attempts=1)
    session._deliveries.list_stale_processing = AsyncMock(return_value=[stale])
    session._deliveries.requeue_stale = AsyncMock(
        return_value=_delivery(status=DeliveryStatus.QUEUED)
    )
    session._deliveries.requeue_due_retrying = AsyncMock(return_value=2)
    session._deliveries.get_queued_orgs = AsyncMock(return_value=[ORG_ID])
    session._deliveries.get_queued_for_org = AsyncMock(return_value=[])
    session.commit = AsyncMock()

    async def run() -> None:
        counters = await worker.sweep_once()
        assert counters["stale_requeued"] == 1
        assert counters["retries_promoted"] == 2
        assert counters["delivered"] == 0

    import asyncio

    asyncio.run(run())


def test_sweep_once_drains_org(monkeypatch) -> None:
    worker, session, _ = _patch_worker(monkeypatch, provider=StubProvider())
    queued = _delivery(status=DeliveryStatus.QUEUED)
    claimed = _delivery(status=DeliveryStatus.PROCESSING, attempts=1)
    session._deliveries.list_stale_processing = AsyncMock(return_value=[])
    session._deliveries.requeue_due_retrying = AsyncMock(return_value=0)
    session._deliveries.get_queued_orgs = AsyncMock(return_value=[ORG_ID])
    session._deliveries.get_queued_for_org = AsyncMock(return_value=[queued])
    session._deliveries.claim = AsyncMock(return_value=claimed)
    session._deliveries.mark_delivered = AsyncMock(
        return_value=_delivery(status=DeliveryStatus.DELIVERED, attempts=1)
    )

    async def run() -> None:
        counters = await worker.sweep_once()
        assert counters["delivered"] == 1

    import asyncio

    asyncio.run(run())


def test_run_loop_skips_when_disabled(monkeypatch) -> None:
    worker, session, _ = _patch_worker(monkeypatch)
    worker._session_factory = lambda: _FakeSessionCM(session)
    monkeypatch.setattr("app.workers.delivery_worker.settings.DELIVERY_ENABLED", False)

    async def run() -> None:
        await worker.run_loop()

    import asyncio

    asyncio.run(run())
    session.commit.assert_not_awaited()


def test_worker_type_is_delivery() -> None:
    assert DeliveryWorker._WORKER_TYPE == "delivery"
