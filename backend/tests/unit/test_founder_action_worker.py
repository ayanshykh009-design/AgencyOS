"""Unit tests for the founder action worker (M8). No database required.

Regression: the worker's heartbeat must be best-effort ("a heartbeat failure
must never take down the worker loop", the repo-wide worker contract) and the
loop's ``finally`` must never reference an unbound ``counters`` when the first
heartbeat of an iteration fails.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.config import settings
from app.workers.founder_action_worker import _WORKER_TYPE, INSTANCE_ID, FounderActionWorker


def _patch_heartbeat(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    heartbeat = AsyncMock()
    session = MagicMock()
    session.commit = AsyncMock()

    class _FakeSessionCM:
        async def __aenter__(self) -> object:
            return session

        async def __aexit__(self, *exc_info: object) -> bool:
            return False

    monkeypatch.setattr(
        "app.workers.founder_action_worker.async_session_factory", lambda: _FakeSessionCM()
    )

    class _FakeHealthService:
        def __init__(self, s: object) -> None:
            pass

    _FakeHealthService.heartbeat = heartbeat
    monkeypatch.setattr(
        "app.workers.founder_action_worker.WorkerHealthService", _FakeHealthService
    )
    return heartbeat


async def test_heartbeat_writes_loop_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    heartbeat = _patch_heartbeat(monkeypatch)

    await FounderActionWorker().heartbeat(loop_ok=True, last_error=None, counters={})

    _, kwargs = heartbeat.await_args
    assert kwargs["worker_type"] == _WORKER_TYPE
    assert kwargs["instance_id"] == INSTANCE_ID
    assert kwargs["loop_ok"] is True
    assert kwargs["last_error"] is None
    assert kwargs["counters"] == {}


async def test_heartbeat_failure_is_best_effort(monkeypatch: pytest.MonkeyPatch) -> None:
    heartbeat = _patch_heartbeat(monkeypatch)
    heartbeat.side_effect = RuntimeError("db down")
    # A heartbeat failure must never raise out of the worker loop.
    await FounderActionWorker().heartbeat(loop_ok=True, last_error=None, counters={})


async def test_run_loop_survives_initial_heartbeat_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The loop keeps running when an iteration's first heartbeat fails.

    Regression for the worker-loop death: before the fix, a failing initial
    heartbeat left ``counters`` unbound and the ``finally`` raised
    ``UnboundLocalError``, killing the loop.
    """
    worker = FounderActionWorker()
    monkeypatch.setattr(settings, "FOUNDER_ASSISTANT_ENABLED", True)
    heartbeat = AsyncMock(side_effect=[RuntimeError("db down"), None])
    monkeypatch.setattr(worker, "heartbeat", heartbeat)
    monkeypatch.setattr(
        FounderActionWorker, "sweep_once", AsyncMock(return_value={"expired": 0})
    )
    sleep = AsyncMock(side_effect=asyncio.CancelledError())
    monkeypatch.setattr("app.workers.founder_action_worker.asyncio.sleep", sleep)

    with pytest.raises(asyncio.CancelledError):
        await worker.run_loop()

    assert heartbeat.await_count == 2
    _, kwargs = heartbeat.await_args
    assert kwargs["loop_ok"] is False
    assert kwargs["last_error"] == "db down"
    assert kwargs["counters"] == {}