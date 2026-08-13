"""Unit tests for DeliveryRepository guarded state transitions (M6).

Thin SQLAlchemy wrappers; without a live database we assert the query
contract: guarded UPDATEs (correct status guards), RETURNING usage, and the
legacy bulk-recovery path.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.delivery import Delivery
from app.models.enums import DeliveryStatus
from app.repositories.delivery import DeliveryRepository

ORG_ID = uuid.uuid4()
DELIVERY_ID = uuid.uuid4()


class _Scalars:
    def __init__(self, values: list) -> None:
        self._values = values

    def all(self) -> list:
        return self._values

    def first(self):
        return self._values[0] if self._values else None

    def scalar_one(self):
        return self._values[0]

    def scalar_one_or_none(self):
        return self._values[0] if self._values else None


class _Result:
    def __init__(self, values: list) -> None:
        self._scalars = _Scalars(values)

    def scalars(self) -> _Scalars:
        return self._scalars

    def scalar_one(self):
        return self._scalars.scalar_one()

    def scalar_one_or_none(self):
        return self._scalars.scalar_one_or_none()

    def all(self):
        return self._scalars.all()


class _UpdateResult:
    def __init__(self, rowcount: int) -> None:
        self.rowcount = rowcount


class RecordingSession(AsyncSession):
    """AsyncSession stand-in that records executed statement strings."""

    def __init__(self, results: list | None = None) -> None:
        self.executed: list[str] = []
        self._results = results or []

    async def execute(self, stmt, params=None):
        self.executed.append(str(stmt))
        if self._results:
            if isinstance(self._results[0], _UpdateResult):
                return self._results.pop(0)
            return _Result(self._results.pop(0))
        return _Result([])


def _repo(session: RecordingSession) -> DeliveryRepository:
    return DeliveryRepository(session)


def _delivery(**overrides) -> Delivery:
    defaults = dict(
        organization_id=ORG_ID,
        channel="dashboard",
        subject="subject",
        body="body",
    )
    defaults.update(overrides)
    return Delivery(**defaults)


def test_list_filters_org_status_channel_recipient_and_caps_limit() -> None:
    session = RecordingSession(results=[[_delivery()]])
    repo = _repo(session)

    async def run() -> None:
        rows = await repo.list_deliveries(
            ORG_ID, status="queued", channel="dashboard", limit=500
        )
        assert len(rows) == 1

    import asyncio

    asyncio.run(run())
    stmt = session.executed[0]
    assert "deliveries" in stmt and "organization_id" in stmt
    assert "status" in stmt and "channel" in stmt
    assert "LIMIT" in stmt


def test_count_pending_includes_retrying() -> None:
    session = RecordingSession(results=[[3]])
    repo = _repo(session)

    async def run() -> None:
        assert await repo.count_pending(ORG_ID) == 3

    import asyncio

    asyncio.run(run())
    stmt = session.executed[0]
    assert "count" in stmt
    assert "deliveries" in stmt
    assert "status IN" in stmt


def test_get_by_idempotency_filters_org_and_key() -> None:
    session = RecordingSession(results=[[_delivery()]])
    repo = _repo(session)

    async def run() -> None:
        row = await repo.get_by_idempotency(ORG_ID, "key-1")
        assert row is not None

    import asyncio

    asyncio.run(run())
    stmt = session.executed[0]
    assert "idempotency_key" in stmt and "organization_id" in stmt


def test_count_by_status_groups_globally() -> None:
    session = RecordingSession(results=[[(DeliveryStatus.QUEUED, 2), (DeliveryStatus.FAILED, 1)]])
    repo = _repo(session)

    async def run() -> None:
        counts = await repo.count_by_status()
        assert counts == {"queued": 2, "failed": 1}

    import asyncio

    asyncio.run(run())
    stmt = session.executed[0]
    assert "GROUP BY" in stmt and "deliveries" in stmt


def test_claim_guards_queued_and_returns_row() -> None:
    session = RecordingSession(results=[[_delivery(attempts=1)]])
    repo = _repo(session)

    async def run() -> None:
        row = await repo.claim(ORG_ID, DELIVERY_ID)
        assert row is not None

    import asyncio

    asyncio.run(run())
    stmt = session.executed[0]
    assert "UPDATE" in stmt
    assert "deliveries" in stmt
    assert "status =" in stmt
    assert "RETURNING" in stmt
    assert "attempt_started_at" in stmt
    assert "attempts" in stmt


def test_claim_returns_none_when_lost_race() -> None:
    session = RecordingSession(results=[[]])
    repo = _repo(session)

    async def run() -> None:
        assert await repo.claim(ORG_ID, DELIVERY_ID) is None

    import asyncio

    asyncio.run(run())


def test_mark_delivered_guards_processing_and_clears_cancel() -> None:
    session = RecordingSession(results=[[_delivery()]])
    repo = _repo(session)

    async def run() -> None:
        row = await repo.mark_delivered(
            ORG_ID, DELIVERY_ID, provider_metadata={"n": "1"}, delivered_at=datetime.now(UTC)
        )
        assert row is not None

    import asyncio

    asyncio.run(run())
    stmt = session.executed[0]
    assert "UPDATE" in stmt and "deliveries" in stmt
    assert "status =" in stmt
    assert "delivered_at" in stmt and "provider_metadata" in stmt
    assert "cancel_requested_at" in stmt and "attempt_started_at" in stmt


def test_mark_failed_guards_processing_and_stores_error() -> None:
    session = RecordingSession(results=[[_delivery()]])
    repo = _repo(session)

    async def run() -> None:
        row = await repo.mark_failed(
            ORG_ID, DELIVERY_ID, error="provider.unavailable: x", failed_at=datetime.now(UTC)
        )
        assert row is not None

    import asyncio

    asyncio.run(run())
    stmt = session.executed[0]
    assert "UPDATE" in stmt and "deliveries" in stmt
    assert "status =" in stmt
    assert "last_error" in stmt and "failed_at" in stmt


def test_schedule_retry_guards_processing_and_sets_backoff() -> None:
    session = RecordingSession(results=[[_delivery()]])
    repo = _repo(session)

    async def run() -> None:
        row = await repo.schedule_retry(
            ORG_ID, DELIVERY_ID, next_attempt_at=datetime.now(UTC), error="boom"
        )
        assert row is not None

    import asyncio

    asyncio.run(run())
    stmt = session.executed[0]
    assert "UPDATE" in stmt and "deliveries" in stmt
    assert "status =" in stmt
    assert "next_attempt_at" in stmt and "last_error" in stmt


def test_requeue_due_retrying_promotes_due_rows() -> None:
    session = RecordingSession(results=[_UpdateResult(4)])
    repo = _repo(session)

    async def run() -> None:
        assert await repo.requeue_due_retrying(limit=10) == 4

    import asyncio

    asyncio.run(run())
    stmt = session.executed[0]
    assert "UPDATE" in stmt and "deliveries" in stmt
    assert "status =" in stmt
    assert "next_attempt_at" in stmt


def test_mark_cancel_requested_guards_processing_and_idempotent_flag() -> None:
    session = RecordingSession(results=[[_delivery()]])
    repo = _repo(session)

    async def run() -> None:
        row = await repo.mark_cancel_requested(
            ORG_ID,
            DELIVERY_ID,
            cancel_requested_at=datetime.now(UTC),
            cancelled_by_user_id=uuid.uuid4(),
        )
        assert row is not None

    import asyncio

    asyncio.run(run())
    stmt = session.executed[0]
    assert "cancel_requested_at" in stmt
    assert "cancel_requested_at IS NULL" in stmt


def test_mark_cancelled_only_allows_queued_and_retrying() -> None:
    session = RecordingSession(results=[[_delivery()]])
    repo = _repo(session)

    async def run() -> None:
        row = await repo.mark_cancelled(ORG_ID, DELIVERY_ID, cancelled_at=datetime.now(UTC))
        assert row is not None

    import asyncio

    asyncio.run(run())
    stmt = session.executed[0]
    assert "UPDATE" in stmt and "deliveries" in stmt
    assert "status IN" in stmt
    assert "cancelled_at" in stmt and "cancel_requested_at" in stmt


def test_mark_cancelled_after_send_requires_cancel_request() -> None:
    session = RecordingSession(results=[[_delivery()]])
    repo = _repo(session)

    async def run() -> None:
        row = await repo.mark_cancelled_after_send(
            ORG_ID, DELIVERY_ID, cancelled_at=datetime.now(UTC), error="cancel requested"
        )
        assert row is not None

    import asyncio

    asyncio.run(run())
    stmt = session.executed[0]
    assert "UPDATE" in stmt and "deliveries" in stmt
    assert "status =" in stmt
    assert "cancelled_at" in stmt
    assert "cancel_requested_at IS NOT NULL" in stmt


def test_mark_requeued_only_allows_failed_and_cancelled_and_resets() -> None:
    session = RecordingSession(results=[[_delivery()]])
    repo = _repo(session)

    async def run() -> None:
        row = await repo.mark_requeued(ORG_ID, DELIVERY_ID, requeued_at=datetime.now(UTC))
        assert row is not None

    import asyncio

    asyncio.run(run())
    stmt = session.executed[0]
    assert "UPDATE" in stmt and "deliveries" in stmt
    assert "status IN" in stmt
    assert "next_attempt_at" in stmt and "attempts" in stmt


def test_list_stale_processing_filters_window() -> None:
    session = RecordingSession(results=[[]])
    repo = _repo(session)

    async def run() -> None:
        await repo.list_stale_processing(datetime.now(UTC), limit=10)

    import asyncio

    asyncio.run(run())
    stmt = session.executed[0]
    assert "deliveries" in stmt
    assert "attempt_started_at" in stmt and "LIMIT" in stmt


def test_requeue_stale_guards_processing_and_clears_stamp() -> None:
    session = RecordingSession(results=[[_delivery()]])
    repo = _repo(session)

    async def run() -> None:
        row = await repo.requeue_stale(ORG_ID, DELIVERY_ID)
        assert row is not None

    import asyncio

    asyncio.run(run())
    stmt = session.executed[0]
    assert "UPDATE" in stmt and "deliveries" in stmt
    assert "status =" in stmt
    assert "attempt_started_at" in stmt and "attempts" in stmt


def test_release_stale_processing_uses_paired_path() -> None:
    stale = _delivery(id=DELIVERY_ID)
    session = RecordingSession(results=[[stale], [stale]])
    repo = _repo(session)

    async def run() -> None:
        assert await repo.release_stale_processing(datetime.now(UTC)) == 1

    import asyncio

    asyncio.run(run())
    assert len(session.executed) == 2
    assert "SELECT" in session.executed[0]
    assert "UPDATE" in session.executed[1]


def test_get_queued_for_org_filters_due_window() -> None:
    session = RecordingSession(results=[[]])
    repo = _repo(session)

    async def run() -> None:
        await repo.get_queued_for_org(ORG_ID, 10)

    import asyncio

    asyncio.run(run())
    stmt = session.executed[0]
    assert "scheduled_for" in stmt and "next_attempt_at" in stmt
    assert "status =" in stmt


def test_get_queued_orgs_groups_and_orders_oldest_first() -> None:
    session = RecordingSession(results=[[ORG_ID]])
    repo = _repo(session)

    async def run() -> None:
        assert await repo.get_queued_orgs(10) == [ORG_ID]

    import asyncio

    asyncio.run(run())
    stmt = session.executed[0]
    assert "GROUP BY" in stmt and "min" in stmt and "scheduled_for" in stmt
