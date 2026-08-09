"""Unit tests for the MemoryWorker cleanup sweep (gating + batching + org scoping)."""
from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

from app.core.metrics import read_counter, reset
from app.workers.memory_worker import MemoryWorker

ORG_A = uuid.UUID("00000000-0000-0000-0000-00000000000a")
ORG_B = uuid.UUID("00000000-0000-0000-0000-00000000000b")


class _FakeSessionCM:
    def __init__(self, session) -> None:
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *args) -> None:
        pass


class _Mem:
    def __init__(self, mid: str) -> None:
        self.id = uuid.uuid5(uuid.NAMESPACE_DNS, mid)


def _patch_worker(
    monkeypatch, *, enabled: bool = True, org_rows, org_batches, deletes
) -> MagicMock:
    session = MagicMock()
    org_result = MagicMock()
    org_result.all = MagicMock(return_value=org_rows)
    session.execute = AsyncMock(side_effect=[MagicMock(), org_result])
    session.commit = AsyncMock()

    instances: list = []

    class _FakeRepo:
        def __init__(self, s: object) -> None:
            self.list_expired_working = AsyncMock(side_effect=org_batches)
            self.delete_many = AsyncMock(side_effect=deletes)
            instances.append(self)

    monkeypatch.setattr(
        "app.workers.memory_worker.async_session_factory",
        lambda: _FakeSessionCM(session),
    )
    monkeypatch.setattr("app.workers.memory_worker.AiMemoryRepository", _FakeRepo)
    monkeypatch.setattr(
        "app.workers.memory_worker.settings",
        MagicMock(
            MEMORY_CLEANUP_ENABLED=enabled,
            MEMORY_WORKING_TTL_DAYS=30,
            MEMORY_CLEANUP_BATCH_SIZE=500,
            EXECUTION_STATEMENT_TIMEOUT_SECONDS=30,
        ),
    )
    session.repos = instances
    return session


def test_cleanup_tick_disabled_returns_zeros(monkeypatch) -> None:
    session = _patch_worker(monkeypatch, enabled=False, org_rows=[], org_batches=[], deletes=[])

    async def run() -> None:
        stats = await MemoryWorker.cleanup_tick()
        assert stats == {"orgs_swept": 0, "expired_deleted": 0}

    asyncio.run(run())
    session.execute.assert_not_called()


def test_cleanup_tick_chunks_per_org_and_aggregates(monkeypatch) -> None:
    reset()
    # Org A fills its batch once (500 → keeps sweeping), then drains a partial
    # (37 → under batch, stops); Org B has nothing expired.
    full_batch = [_Mem(f"a{i}") for i in range(500)]
    session = _patch_worker(
        monkeypatch,
        org_rows=[(ORG_A,), (ORG_B,)],
        org_batches=[full_batch, [_Mem("a-500"), _Mem("a-501")], []],
        deletes=[500, 37],
    )

    async def run() -> None:
        stats = await MemoryWorker.cleanup_tick()
        assert stats == {"orgs_swept": 2, "expired_deleted": 537}

    asyncio.run(run())
    repo = session.repos[0]
    assert repo.list_expired_working.await_count == 3
    assert repo.delete_many.await_count == 2
    session.commit.assert_awaited_once()
    assert read_counter("agencyos.memory.cleanup.expired_total") == 537


def test_cleanup_tick_single_batch_when_under_limit(monkeypatch) -> None:
    reset()
    session = _patch_worker(
        monkeypatch,
        org_rows=[(ORG_A,)],
        org_batches=[[_Mem("a1")], []],
        deletes=[1, 0],
    )

    async def run() -> None:
        stats = await MemoryWorker.cleanup_tick()
        assert stats == {"orgs_swept": 1, "expired_deleted": 1}

    asyncio.run(run())
    assert read_counter("agencyos.memory.cleanup.expired_total") == 1
    session.commit.assert_awaited_once()


def test_cleanup_tick_no_counter_when_nothing_deleted(monkeypatch) -> None:
    reset()
    session = _patch_worker(
        monkeypatch,
        org_rows=[(ORG_A,)],
        org_batches=[[]],
        deletes=[],
    )

    async def run() -> None:
        stats = await MemoryWorker.cleanup_tick()
        assert stats == {"orgs_swept": 1, "expired_deleted": 0}

    asyncio.run(run())
    assert read_counter("agencyos.memory.cleanup.expired_total") == 0
    session.commit.assert_awaited_once()
