"""Unit tests for the approval gate worker. No database required.

Regression (B-4): the worker's heartbeat must be best-effort ("a heartbeat
failure must never take down the worker loop", the repo-wide worker contract)
and the loop's ``finally`` must never reference an unbound ``counters`` when
the first heartbeat of an iteration fails (UnboundLocalError crash).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.config import settings
from app.workers.approval_gate_worker import INSTANCE_ID, ApprovalGateWorker


def _session_factory() -> MagicMock:
    session = MagicMock()
    session.commit = AsyncMock()

    class _CM:
        async def __aenter__(self) -> object:
            return session

        async def __aexit__(self, *exc_info: object) -> bool:
            return False

    return _CM()  # type: ignore[return-value]


def _patch_health(monkeypatch: pytest.MonkeyPatch, heartbeat: AsyncMock) -> None:
    health_cls = MagicMock()
    health_cls.return_value.heartbeat = heartbeat
    monkeypatch.setattr("app.workers.approval_gate_worker.WorkerHealthService", health_cls)


async def test_heartbeat_writes_loop_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    heartbeat = AsyncMock()
    _patch_health(monkeypatch, heartbeat)

    await ApprovalGateWorker(session_factory=_session_factory).heartbeat(
        loop_ok=True, last_error=None, counters={"handled": 2}
    )

    _, kwargs = heartbeat.await_args
    assert kwargs["worker_type"] == "approval_gate"
    assert kwargs["instance_id"] == INSTANCE_ID
    assert kwargs["loop_ok"] is True
    assert kwargs["last_error"] is None
    assert kwargs["counters"] == {"handled": 2}


async def test_heartbeat_failure_is_best_effort(monkeypatch: pytest.MonkeyPatch) -> None:
    heartbeat = AsyncMock(side_effect=RuntimeError("db down"))
    _patch_health(monkeypatch, heartbeat)
    # A heartbeat failure must never raise out of the worker loop.
    await ApprovalGateWorker(session_factory=_session_factory).heartbeat(
        loop_ok=True, last_error=None, counters={}
    )


async def test_run_loop_survives_initial_heartbeat_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression (B-4): a failing first heartbeat must not crash the loop.

    Before the fix, an initial-heartbeat exception left ``counters`` unbound
    and the ``finally`` raised UnboundLocalError, killing the loop with a
    misleading error instead of reporting the heartbeat failure.
    """
    monkeypatch.setattr(settings, "DELIVERY_ENABLED", True)
    worker = ApprovalGateWorker(session_factory=_session_factory)
    heartbeat = AsyncMock(side_effect=[RuntimeError("db down"), None])
    monkeypatch.setattr(worker, "heartbeat", heartbeat)
    monkeypatch.setattr(
        ApprovalGateWorker, "sweep_once", AsyncMock(return_value={"handled": 0})
    )
    sleep = AsyncMock(side_effect=asyncio.CancelledError())
    monkeypatch.setattr("app.workers.approval_gate_worker.asyncio.sleep", sleep)

    with pytest.raises(asyncio.CancelledError):
        await worker.run_loop()

    # Both heartbeats attempted; the finally one reports the failure, not crash.
    assert heartbeat.await_count == 2
    _, kwargs = heartbeat.await_args
    assert kwargs["loop_ok"] is False
    assert kwargs["last_error"] == "db down"
    assert kwargs["counters"] == {}


async def test_run_loop_reports_sweep_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """A sweep failure is surfaced through the finally heartbeat, loop continues."""
    monkeypatch.setattr(settings, "DELIVERY_ENABLED", True)
    worker = ApprovalGateWorker(session_factory=_session_factory)
    heartbeat = AsyncMock()
    monkeypatch.setattr(worker, "heartbeat", heartbeat)
    monkeypatch.setattr(
        ApprovalGateWorker,
        "sweep_once",
        AsyncMock(side_effect=RuntimeError("gate sweep down")),
    )
    sleep = AsyncMock(side_effect=asyncio.CancelledError())
    monkeypatch.setattr("app.workers.approval_gate_worker.asyncio.sleep", sleep)

    with pytest.raises(asyncio.CancelledError):
        await worker.run_loop()

    assert heartbeat.await_count == 2
    _, kwargs = heartbeat.await_args
    assert kwargs["loop_ok"] is False
    assert kwargs["last_error"] == "gate sweep down"


async def test_run_loop_heartbeat_failure_never_kills_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even if the health-service writes fail, the loop keeps sweeping.

    Exercises the REAL best-effort ``heartbeat()`` (try/except inside) — the
    loop must continue when the underlying WorkerHealthService raises.
    """
    monkeypatch.setattr(settings, "DELIVERY_ENABLED", True)

    class _BoomHealth:
        def __init__(self, s: object) -> None:
            pass

        async def heartbeat(self, **kwargs: object) -> None:
            raise RuntimeError("hb down")

    monkeypatch.setattr("app.workers.approval_gate_worker.WorkerHealthService", _BoomHealth)
    worker = ApprovalGateWorker(session_factory=_session_factory)
    sweep = AsyncMock(return_value={"handled": 1})
    monkeypatch.setattr(ApprovalGateWorker, "sweep_once", sweep)

    iterations = 0

    async def _sleep(_seconds: float) -> None:
        nonlocal iterations
        iterations += 1
        if iterations >= 2:
            raise asyncio.CancelledError()

    monkeypatch.setattr("app.workers.approval_gate_worker.asyncio.sleep", _sleep)

    with pytest.raises(asyncio.CancelledError):
        await worker.run_loop()

    assert sweep.await_count == 2


async def test_run_loop_skipped_when_delivery_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "DELIVERY_ENABLED", False)
    worker = ApprovalGateWorker(session_factory=_session_factory)
    heartbeat = AsyncMock()
    monkeypatch.setattr(worker, "heartbeat", heartbeat)

    await worker.run_loop()

    heartbeat.assert_not_awaited()


async def test_sweep_once_returns_handled_count(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeGateService:
        def __init__(self, s: object) -> None:
            pass

        async def sweep(self, limit: int) -> int:
            assert limit == 50
            return 3

    monkeypatch.setattr(
        "app.workers.approval_gate_worker.ApprovalGateService", _FakeGateService
    )
    worker = ApprovalGateWorker(session_factory=_session_factory)

    counters = await worker.run_once()

    assert counters == {"handled": 3}
