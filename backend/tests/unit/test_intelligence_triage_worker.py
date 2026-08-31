"""Unit tests for the intelligence triage worker (M9). No database required.

Regression: the worker's heartbeat must be best-effort ("a heartbeat failure
must never take down the worker loop", the repo-wide worker contract).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.workers.intelligence_triage_worker import (
    _WORKER_TYPE,
    INSTANCE_ID,
    IntelligenceTriageWorker,
)


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
        "app.workers.intelligence_triage_worker.async_session_factory",
        lambda: _FakeSessionCM(),
    )

    class _FakeHealthService:
        def __init__(self, s: object) -> None:
            pass

    _FakeHealthService.heartbeat = heartbeat
    monkeypatch.setattr(
        "app.workers.intelligence_triage_worker.WorkerHealthService", _FakeHealthService
    )
    return heartbeat


async def test_heartbeat_writes_loop_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    heartbeat = _patch_heartbeat(monkeypatch)

    await IntelligenceTriageWorker().heartbeat(loop_ok=True, last_error=None, counters={})

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
    await IntelligenceTriageWorker().heartbeat(loop_ok=True, last_error=None, counters={})