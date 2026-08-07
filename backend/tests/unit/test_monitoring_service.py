"""Unit tests for the WorkerHealthService (heartbeat + liveness delegation)."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from app.services.monitoring_service import WorkerHealthService

ORG_ID = uuid.uuid4()


def _service() -> WorkerHealthService:
    session = MagicMock()
    service = WorkerHealthService(session)
    service._repo = MagicMock()
    return service


async def test_heartbeat_delegates_upsert_with_instance_metadata() -> None:
    service = _service()
    service._repo.upsert = AsyncMock()

    await service.heartbeat(
        worker_type="execution",
        instance_id=ORG_ID,
        loop_ok=True,
        last_error=None,
        counters={"execution_drained_total": 3},
        heartbeat_at=datetime(2026, 8, 5, tzinfo=UTC),
    )

    _, kwargs = service._repo.upsert.await_args
    assert kwargs["worker_type"] == "execution"
    assert kwargs["instance_id"] == ORG_ID
    assert kwargs["loop_ok"] is True
    assert kwargs["last_error"] is None
    assert kwargs["counters"] == {"execution_drained_total": 3}
    assert kwargs["heartbeat_at"] == datetime(2026, 8, 5, tzinfo=UTC)
    assert kwargs["pid"] > 0
    assert kwargs["hostname"]


async def test_heartbeat_defaults_counters_to_empty() -> None:
    service = _service()
    service._repo.upsert = AsyncMock()

    await service.heartbeat(
        worker_type="execution",
        instance_id=ORG_ID,
        loop_ok=False,
        last_error="boom",
    )

    _, kwargs = service._repo.upsert.await_args
    assert kwargs["counters"] == {}
    assert kwargs["loop_ok"] is False
    assert kwargs["last_error"] == "boom"


async def test_list_alive_and_count_stale_delegate() -> None:
    service = _service()
    service._repo.list_alive = AsyncMock(return_value=[MagicMock()])
    service._repo.count_stale = AsyncMock(return_value=4)

    alive = await service.list_alive(
        "execution", stale_within_seconds=15, limit=10
    )
    stale = await service.count_stale(
        stale_within_seconds=15, worker_type="execution"
    )

    assert len(alive) == 1
    assert stale == 4
    service._repo.list_alive.assert_awaited_once_with(
        "execution", stale_within_seconds=15, limit=10
    )
    service._repo.count_stale.assert_awaited_once_with(
        stale_within_seconds=15, worker_type="execution"
    )


async def test_prune_dead_delegates() -> None:
    service = _service()
    service._repo.delete_stale_older_than = AsyncMock(return_value=9)

    pruned = await service.prune_dead(
        datetime(2026, 5, 1, tzinfo=UTC), batch=100
    )

    assert pruned == 9
    service._repo.delete_stale_older_than.assert_awaited_once_with(
        datetime(2026, 5, 1, tzinfo=UTC), 100
    )
