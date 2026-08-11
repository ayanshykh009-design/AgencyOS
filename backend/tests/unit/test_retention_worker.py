"""Unit tests for the RetentionWorker sweep (boundary + batching + gating)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from app.core.metrics import read_counter, reset
from app.workers.retention_worker import RetentionWorker


class _FakeSessionCM:
    def __init__(self, session) -> None:
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *args) -> None:
        pass


def _patch_retention(monkeypatch, *, enabled: bool = True, deletes) -> MagicMock:
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()

    exec_delete = AsyncMock(side_effect=deletes)
    delivery_delete = AsyncMock(return_value=0)
    prune_dead = AsyncMock(return_value=2)

    class _FakeEventsRepo:
        def __init__(self, s: object) -> None:
            pass

    class _FakeDeliveryEventsRepo:
        def __init__(self, s: object) -> None:
            pass

    class _FakeHealthService:
        def __init__(self, s: object) -> None:
            pass

    _FakeEventsRepo.delete_older_than = exec_delete
    _FakeDeliveryEventsRepo.delete_older_than = delivery_delete
    _FakeHealthService.prune_dead = prune_dead

    monkeypatch.setattr(
        "app.workers.retention_worker.async_session_factory",
        lambda: _FakeSessionCM(session),
    )
    monkeypatch.setattr(
        "app.workers.retention_worker.ExecutionEventRepository", _FakeEventsRepo
    )
    monkeypatch.setattr(
        "app.workers.retention_worker.DeliveryEventRepository", _FakeDeliveryEventsRepo
    )
    monkeypatch.setattr(
        "app.workers.retention_worker.WorkerHealthService", _FakeHealthService
    )
    monkeypatch.setattr(
        "app.workers.retention_worker.settings",
        MagicMock(
            EXECUTION_RETENTION_ENABLED=enabled,
            EXECUTION_EVENT_RETENTION_DAYS=90,
            EXECUTION_RETENTION_BATCH=1000,
            EXECUTION_STATEMENT_TIMEOUT_SECONDS=30,
            DELIVERY_RETENTION_ENABLED=True,
            DELIVERY_EVENT_RETENTION_DAYS=90,
            DELIVERY_RETENTION_BATCH=1000,
        ),
    )
    session.exec_delete = exec_delete
    session.delivery_delete = delivery_delete
    session.prune_dead = prune_dead
    return session


def test_retention_tick_disabled_returns_zeros(monkeypatch) -> None:
    session = _patch_retention(monkeypatch, enabled=False, deletes=[])

    async def run() -> None:
        stats = await RetentionWorker.retention_tick()
        assert stats == {
            "executions_deleted": 0,
            "delivery_events_deleted": 0,
            "workers_pruned": 0,
        }

    import asyncio

    asyncio.run(run())
    session.execute.assert_not_called()


def test_retention_tick_chunks_until_under_batch(monkeypatch) -> None:
    reset()
    # First delete returns the full batch, second returns less: the loop stops.
    session = _patch_retention(monkeypatch, deletes=[1000, 37])

    async def run() -> None:
        stats = await RetentionWorker.retention_tick()
        assert stats == {
            "executions_deleted": 1037,
            "delivery_events_deleted": 0,
            "workers_pruned": 2,
        }

    import asyncio

    asyncio.run(run())
    assert session.exec_delete.await_count == 2
    session.commit.assert_awaited_once()
    assert read_counter("retention_deleted_total") == 1039


def test_retention_tick_single_batch_when_under_limit(monkeypatch) -> None:
    reset()
    session = _patch_retention(monkeypatch, deletes=[50])

    async def run() -> None:
        stats = await RetentionWorker.retention_tick()
        assert stats == {
            "executions_deleted": 50,
            "delivery_events_deleted": 0,
            "workers_pruned": 2,
        }

    import asyncio

    asyncio.run(run())
    assert session.exec_delete.await_count == 1
    session.commit.assert_awaited_once()
    assert read_counter("retention_deleted_total") == 52


def test_retention_tick_purges_delivery_events(monkeypatch) -> None:
    reset()
    session = _patch_retention(monkeypatch, deletes=[0])
    session.prune_dead.return_value = 0
    session.delivery_delete.return_value = 64

    async def run() -> None:
        stats = await RetentionWorker.retention_tick()
        assert stats == {
            "executions_deleted": 0,
            "delivery_events_deleted": 64,
            "workers_pruned": 0,
        }

    import asyncio

    asyncio.run(run())
    session.delivery_delete.assert_awaited_once()
    assert read_counter("retention_delivery_events_deleted_total") == 64


def test_retention_tick_no_counter_when_nothing_deleted(monkeypatch) -> None:
    reset()
    session = _patch_retention(monkeypatch, deletes=[0])
    session.prune_dead.return_value = 0

    async def run() -> None:
        stats = await RetentionWorker.retention_tick()
        assert stats == {
            "executions_deleted": 0,
            "delivery_events_deleted": 0,
            "workers_pruned": 0,
        }

    import asyncio

    asyncio.run(run())
    assert read_counter("retention_deleted_total") == 0
    session.commit.assert_awaited_once()
