"""Unit tests: AgentWorker sweep logic with a fake session + runtime."""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, call

import pytest

from app.core.errors import AppError
from app.models.enums import AgentRunStatus
from app.workers.agent_worker import AgentWorker

ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
RUN_ID = uuid.UUID("00000000-0000-0000-0000-000000000101")


class FakeSession:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


class FakeSessionCM:
    def __init__(self, session: FakeSession) -> None:
        self._session = session

    async def __aenter__(self) -> FakeSession:
        return self._session

    async def __aexit__(self, *exc_info: object) -> bool:
        return False


def _run(**overrides: object) -> SimpleNamespace:
    run = SimpleNamespace(
        id=RUN_ID,
        organization_id=ORG_ID,
        agent_name="research_agent",
        status=AgentRunStatus.QUEUED,
        input={"goal": "research this lead"},
    )
    for key, value in overrides.items():
        setattr(run, key, value)
    return run


def _worker_settings(
    *, enabled: bool = True, batch_size: int = 10, orgs_per_sweep: int = 20
) -> SimpleNamespace:
    return SimpleNamespace(
        AGENT_RUNTIME_ENABLED=enabled,
        AGENT_RUN_POLL_INTERVAL_SECONDS=5,
        AGENT_RUN_BATCH_SIZE=batch_size,
        AGENT_RUN_ORGS_PER_SWEEP=orgs_per_sweep,
    )


def _patch_settings(
    monkeypatch: pytest.MonkeyPatch,
    *,
    enabled: bool = True,
    batch_size: int = 10,
    orgs_per_sweep: int = 20,
) -> None:
    monkeypatch.setattr(
        "app.workers.agent_worker.settings",
        _worker_settings(
            enabled=enabled, batch_size=batch_size, orgs_per_sweep=orgs_per_sweep
        ),
    )


def _patch_session(monkeypatch: pytest.MonkeyPatch) -> FakeSession:
    session = FakeSession()
    monkeypatch.setattr(
        "app.workers.agent_worker.async_session_factory",
        lambda: FakeSessionCM(session),
    )
    return session


def _patch_runtime(
    monkeypatch: pytest.MonkeyPatch,
    *,
    final: object | None = None,
    side_effect: list | None = None,
) -> AsyncMock:
    execute = AsyncMock(return_value=final, side_effect=side_effect)
    monkeypatch.setattr(
        "app.workers.agent_worker.AgentRuntime",
        type("R", (), {"execute_run": execute}),
    )
    return execute


class FakeAgentService:
    get_queued_orgs: AsyncMock
    get_queued_for_org: AsyncMock
    get_cancel_requested: AsyncMock
    get_stuck_running: AsyncMock
    apply_cancel: AsyncMock
    fail_run: AsyncMock

    def __init__(self, session: object) -> None:
        pass


def _patch_service(
    monkeypatch: pytest.MonkeyPatch,
    *,
    orgs: list | None = None,
    queued: list | None = None,
    cancel_requested: list | None = None,
    stuck: list | None = None,
    apply_cancel_raises: bool = False,
    fail_run_raises: bool = False,
) -> type[FakeAgentService]:
    FakeAgentService.get_queued_orgs = AsyncMock(return_value=orgs or [ORG_ID])
    FakeAgentService.get_queued_for_org = AsyncMock(return_value=queued or [])
    FakeAgentService.get_cancel_requested = AsyncMock(
        return_value=cancel_requested or []
    )
    FakeAgentService.get_stuck_running = AsyncMock(return_value=stuck or [])
    FakeAgentService.apply_cancel = AsyncMock()
    FakeAgentService.fail_run = AsyncMock()
    if apply_cancel_raises:
        FakeAgentService.apply_cancel.side_effect = AppError(
            code="agent_run.invalid_state",
            message="Agent run state changed concurrently",
            status_code=409,
        )
    if fail_run_raises:
        FakeAgentService.fail_run.side_effect = AppError(
            code="agent_run.invalid_state",
            message="Agent run state changed concurrently",
            status_code=409,
        )
    monkeypatch.setattr("app.workers.agent_worker.AgentService", FakeAgentService)
    return FakeAgentService


class TestSweepGate:
    async def test_sweep_disabled_is_a_noop(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_settings(monkeypatch, enabled=False)
        for name in ("process_queued", "process_cancels", "reconcile_stuck"):
            monkeypatch.setattr(AgentWorker, name, AsyncMock())

        stats = await AgentWorker.sweep()

        assert all(value == 0 for value in stats.values())
        for name in ("process_queued", "process_cancels", "reconcile_stuck"):
            assert not getattr(AgentWorker, name).called

    async def test_sweep_runs_all_phases(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_settings(monkeypatch, enabled=True)
        monkeypatch.setattr(AgentWorker, "process_queued", AsyncMock(return_value=3))
        monkeypatch.setattr(AgentWorker, "process_cancels", AsyncMock(return_value=1))
        monkeypatch.setattr(AgentWorker, "reconcile_stuck", AsyncMock(return_value=2))

        stats = await AgentWorker.sweep()

        assert stats == {"processed": 3, "cancelled": 1, "stuck": 2}


class TestProcessQueued:
    async def test_drains_orgs_fairly(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_settings(monkeypatch)
        session = _patch_session(monkeypatch)
        other_org = uuid.UUID("00000000-0000-0000-0000-000000000002")
        runs_org1 = [_run()]
        runs_org2 = [_run(), _run()]
        service = _patch_service(monkeypatch, orgs=[ORG_ID, other_org])
        service.get_queued_for_org = AsyncMock(
            side_effect=lambda org_id, limit: runs_org1
            if org_id == ORG_ID
            else runs_org2
        )
        _patch_runtime(monkeypatch, final=_run(status=AgentRunStatus.SUCCEEDED))

        processed = await AgentWorker.process_queued()

        assert processed == 3
        assert service.get_queued_orgs.await_args_list[0].args == (20,)
        assert service.get_queued_for_org.await_args_list == [
            call(ORG_ID, 10),
            call(other_org, 10),
        ]
        assert session.committed is True

    async def test_skips_runs_claimed_elsewhere(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_settings(monkeypatch)
        _patch_session(monkeypatch)
        service = _patch_service(monkeypatch, queued=[_run()])
        _patch_runtime(monkeypatch, final=None)

        processed = await AgentWorker.process_queued()

        assert processed == 0
        assert service.get_queued_for_org.await_count == 1

    async def test_rolls_back_and_continues_on_unexpected_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_settings(monkeypatch)
        session = _patch_session(monkeypatch)
        _patch_service(monkeypatch, queued=[_run(), _run()])
        _patch_runtime(
            monkeypatch,
            side_effect=[
                RuntimeError("boom"),
                _run(status=AgentRunStatus.SUCCEEDED),
            ],
        )

        processed = await AgentWorker.process_queued()

        assert processed == 1
        assert session.rolled_back is True
        assert session.committed is True


class TestProcessCancels:
    async def test_applies_cancel_flags(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_settings(monkeypatch)
        session = _patch_session(monkeypatch)
        service = _patch_service(
            monkeypatch,
            cancel_requested=[_run(), _run(status=AgentRunStatus.CANCELLED)],
        )

        cancelled = await AgentWorker.process_cancels()

        assert cancelled == 2
        assert service.apply_cancel.await_count == 2
        assert session.committed is True

    async def test_skips_runs_whose_state_changed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_settings(monkeypatch)
        _patch_session(monkeypatch)
        _patch_service(
            monkeypatch, cancel_requested=[_run(), _run()], apply_cancel_raises=True
        )

        cancelled = await AgentWorker.process_cancels()

        assert cancelled == 0


class TestReconcileStuck:
    async def test_fails_stale_runs(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_settings(monkeypatch)
        session = _patch_session(monkeypatch)
        service = _patch_service(monkeypatch, stuck=[_run()])

        transitioned = await AgentWorker.reconcile_stuck()

        assert transitioned == 1
        assert service.fail_run.await_args_list[0].kwargs["error"] == (
            "Agent run exceeded its time budget"
        )
        assert session.committed is True

    async def test_skips_runs_already_transitioned(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_settings(monkeypatch)
        _patch_session(monkeypatch)
        _patch_service(monkeypatch, stuck=[_run()], fail_run_raises=True)

        transitioned = await AgentWorker.reconcile_stuck()

        assert transitioned == 0


class TestRunLoop:
    async def test_loop_exits_when_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_settings(monkeypatch, enabled=False)
        sweep = AsyncMock()
        heartbeat = AsyncMock()
        monkeypatch.setattr(AgentWorker, "sweep", sweep)
        monkeypatch.setattr(AgentWorker, "heartbeat", heartbeat)

        await AgentWorker.run_loop()

        sweep.assert_not_called()
        heartbeat.assert_not_called()

    async def test_loop_heartbeats_and_sleeps(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_settings(monkeypatch, enabled=True)
        sweep = AsyncMock(side_effect=[{"processed": 1}, KeyboardInterrupt()])
        heartbeat = AsyncMock()
        sleep = AsyncMock()
        monkeypatch.setattr(AgentWorker, "sweep", sweep)
        monkeypatch.setattr(AgentWorker, "heartbeat", heartbeat)
        monkeypatch.setattr("app.workers.agent_worker.asyncio.sleep", sleep)

        with pytest.raises(KeyboardInterrupt):
            await AgentWorker.run_loop()

        assert sweep.await_count == 2
        assert heartbeat.await_args_list == [
            call(loop_ok=True, last_error=None),
            call(loop_ok=False, last_error="shutdown"),
        ]
        assert sleep.await_count == 1
