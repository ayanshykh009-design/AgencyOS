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

    delete_older_than = AsyncMock(side_effect=deletes)
    prune_dead = AsyncMock(return_value=2)

    class _FakeEventsRepo:
        def __init__(self, s: object) -> None:
            pass

    class _FakeHealthService:
        def __init__(self, s: object) -> None:
            pass

    _FakeEventsRepo.delete_older_than = delete_older_than
    _FakeHealthService.prune_dead = prune_dead

    monkeypatch.setattr(
        "app.workers.retention_worker.async_session_factory",
        lambda: _FakeSessionCM(session),
    )
    monkeypatch.setattr(
        "app.workers.retention_worker.ExecutionEventRepository", _FakeEventsRepo
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
        ),
    )
    session.delete_older_than = delete_older_than
    session.prune_dead = prune_dead
    return session


def test_retention_tick_disabled_returns_zeros(monkeypatch) -> None:
    session = _patch_retention(monkeypatch, enabled=False, deletes=[])

    async def run() -> None:
        stats = await RetentionWorker.retention_tick()
        assert stats == {"events_deleted": 0, "workers_pruned": 0}

    import asyncio

    asyncio.run(run())
    session.execute.assert_not_called()


def test_retention_tick_chunks_until_under_batch(monkeypatch) -> None:
    reset()
    # First delete returns the full batch, second returns less: the loop stops.
    session = _patch_retention(monkeypatch, deletes=[1000, 37])

    async def run() -> None:
        stats = await RetentionWorker.retention_tick()
        assert stats == {"events_deleted": 1037, "workers_pruned": 2}

    import asyncio

    asyncio.run(run())
    assert session.delete_older_than.await_count == 2
    session.commit.assert_awaited_once()
    assert read_counter("retention_deleted_total") == 1039


def test_retention_tick_single_batch_when_under_limit(monkeypatch) -> None:
    reset()
    session = _patch_retention(monkeypatch, deletes=[50])

    async def run() -> None:
        stats = await RetentionWorker.retention_tick()
        assert stats == {"events_deleted": 50, "workers_pruned": 2}

    import asyncio

    asyncio.run(run())
    assert session.delete_older_than.await_count == 1
    session.commit.assert_awaited_once()
    assert read_counter("retention_deleted_total") == 52


def test_retention_tick_no_counter_when_nothing_deleted(monkeypatch) -> None:
    reset()
    session = _patch_retention(monkeypatch, deletes=[0])
    session.prune_dead.return_value = 0

    async def run() -> None:
        stats = await RetentionWorker.retention_tick()
        assert stats == {"events_deleted": 0, "workers_pruned": 0}

    import asyncio

    asyncio.run(run())
    assert read_counter("retention_deleted_total") == 0
    session.commit.assert_awaited_once()
