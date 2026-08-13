"""Service-layer unit tests for the M5 agent run runtime lifecycle.

Covers the business rules that live in ``AgentService``: the registry gate on
creation, idempotent creation, runtime-owned status transitions (guarded repo
calls), cancellation semantics (QUEUED -> CANCELLED immediately, RUNNING ->
flag-and-honour), and metadata-only updates. Repositories are mocked; no
database is involved.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.errors import AppError
from app.models.agent_run import AgentRun
from app.models.enums import AgentRunStatus, AgentRunTrigger
from app.services.agent_service import AgentService

ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
AGENT = "founder_assistant"
AGENT_ID = uuid.uuid4()


class FakeSession:
    def __init__(self) -> None:
        self.committed = False
        self.added: list[object] = []

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        pass

    async def flush(self) -> None:
        pass

    async def refresh(self, instance: object) -> None:
        pass


class _FlushFailsSession(FakeSession):
    async def flush(self) -> None:
        raise IntegrityError("insert into agent_runs", {}, Exception("duplicate key"))


def _service() -> tuple[FakeSession, AgentService, MagicMock]:
    session = FakeSession()
    service = AgentService(session)
    runs = MagicMock(name="runs")
    service._runs = runs
    return session, service, runs


def _run(
    status: AgentRunStatus,
    *,
    cancel_requested_at: datetime | None = None,
    started_at: datetime | None = None,
) -> AgentRun:
    return AgentRun(
        id=AGENT_ID,
        organization_id=ORG_ID,
        agent_name=AGENT,
        status=status,
        trigger=AgentRunTrigger.MANUAL,
        cancel_requested_at=cancel_requested_at,
        started_at=started_at,
    )


# -- creation / registry gate / idempotency ------------------------------


@pytest.mark.asyncio
async def test_create_run_rejects_unknown_agent_404() -> None:
    session, service, runs = _service()
    with pytest.raises(AppError) as exc:
        await service.create_run(ORG_ID, agent_name="not-a-real-agent", input_={})
    assert exc.value.status_code == 404
    assert exc.value.code == "agent.unknown"
    runs.add.assert_not_called()


@pytest.mark.asyncio
async def test_create_run_rejects_future_only_agent_409() -> None:
    session, service, runs = _service()
    with pytest.raises(AppError) as exc:
        await service.create_run(ORG_ID, agent_name="finance", input_={})
    assert exc.value.status_code == 409
    assert exc.value.code == "agent.not_executable"


@pytest.mark.asyncio
async def test_create_run_rejects_non_queued_initial_status_400() -> None:
    session, service, runs = _service()
    with pytest.raises(AppError) as exc:
        await service.create_run(
            ORG_ID, agent_name=AGENT, status=AgentRunStatus.RUNNING, input_={}
        )
    assert exc.value.status_code == 400
    assert exc.value.code == "agent_run.invalid_initial_status"


@pytest.mark.asyncio
async def test_create_run_persists_queued_run() -> None:
    session, service, runs = _service()
    run = await service.create_run(
        ORG_ID, agent_name=AGENT, input_={"goal": "plan my week"}
    )
    assert run.status is AgentRunStatus.QUEUED
    assert run.agent_name == AGENT
    assert run.input == {"goal": "plan my week"}
    assert session.committed is True
    added_run = runs.add.call_args.args[0]
    assert isinstance(added_run, AgentRun)
    assert added_run.status is AgentRunStatus.QUEUED


@pytest.mark.asyncio
async def test_create_run_returns_existing_when_idempotency_key_matches() -> None:
    session, service, runs = _service()
    existing = _run(AgentRunStatus.QUEUED)
    runs.get_by_idempotency_key = AsyncMock(return_value=existing)

    result = await service.create_run(
        ORG_ID, agent_name=AGENT, input_={}, idempotency_key="weekly-plan-2026-08"
    )

    assert result is existing
    runs.get_by_idempotency_key.assert_awaited_once_with(ORG_ID, "weekly-plan-2026-08")
    assert session.added == []


@pytest.mark.asyncio
async def test_create_run_duplicate_key_conflict_409() -> None:
    session = _FlushFailsSession()
    service = AgentService(session)
    runs = MagicMock(name="runs")
    runs.get_by_idempotency_key = AsyncMock(return_value=None)
    service._runs = runs

    with pytest.raises(AppError) as exc:
        await service.create_run(
            ORG_ID, agent_name=AGENT, input_={}, idempotency_key="weekly-plan-2026-08"
        )
    assert exc.value.status_code == 409
    assert exc.value.code == "agent_run.duplicate_idempotency_key"


# -- lifecycle transitions --------------------------------------------------


@pytest.mark.asyncio
async def test_start_run_marks_running() -> None:
    session, service, runs = _service()
    runs.get_or_404 = AsyncMock(return_value=_run(AgentRunStatus.QUEUED))
    claimed = _run(AgentRunStatus.RUNNING, started_at=datetime.now(UTC))
    runs.mark_started = AsyncMock(return_value=claimed)

    result = await service.start_run(ORG_ID, AGENT_ID)

    assert result.status is AgentRunStatus.RUNNING
    runs.mark_started.assert_awaited_once()
    assert session.committed is True


@pytest.mark.asyncio
async def test_start_run_conflict_409_when_not_claimable() -> None:
    session, service, runs = _service()
    runs.get_or_404 = AsyncMock(return_value=_run(AgentRunStatus.QUEUED))
    runs.mark_started = AsyncMock(return_value=None)

    with pytest.raises(AppError) as exc:
        await service.start_run(ORG_ID, AGENT_ID)
    assert exc.value.status_code == 409
    assert exc.value.code == "agent_run.invalid_state"


@pytest.mark.asyncio
async def test_complete_run_succeeds() -> None:
    session, service, runs = _service()
    started = datetime.now(UTC) - timedelta(seconds=5)
    runs.get_or_404 = AsyncMock(
        return_value=_run(AgentRunStatus.RUNNING, started_at=started)
    )
    done = _run(AgentRunStatus.SUCCEEDED, started_at=started)
    runs.mark_succeeded = AsyncMock(return_value=done)

    result = await service.complete_run(
        ORG_ID, AGENT_ID, output={"plan": "done"}, cost=None
    )

    assert result.status is AgentRunStatus.SUCCEEDED
    assert result.duration_ms is not None and result.duration_ms >= 4000
    assert session.committed is True


@pytest.mark.asyncio
async def test_complete_run_honours_concurrent_cancel() -> None:
    session, service, runs = _service()
    started = datetime.now(UTC) - timedelta(seconds=1)
    flagged = _run(
        AgentRunStatus.RUNNING,
        started_at=started,
        cancel_requested_at=datetime.now(UTC),
    )
    runs.get_or_404 = AsyncMock(return_value=flagged)
    runs.mark_succeeded = AsyncMock(return_value=None)
    cancelled = _run(AgentRunStatus.CANCELLED, started_at=started)
    runs.mark_cancelled_after_run = AsyncMock(return_value=cancelled)

    result = await service.complete_run(ORG_ID, AGENT_ID, output={})

    assert result.status is AgentRunStatus.CANCELLED
    runs.mark_cancelled_after_run.assert_awaited_once()


@pytest.mark.asyncio
async def test_fail_run_fails() -> None:
    session, service, runs = _service()
    runs.get_or_404 = AsyncMock(return_value=_run(AgentRunStatus.RUNNING))
    failed = _run(AgentRunStatus.FAILED)
    runs.mark_failed = AsyncMock(return_value=failed)

    result = await service.fail_run(ORG_ID, AGENT_ID, error="boom")

    assert result.status is AgentRunStatus.FAILED
    runs.mark_failed.assert_awaited_once()
    assert session.committed is True


@pytest.mark.asyncio
async def test_fail_run_honours_cancel_request() -> None:
    session, service, runs = _service()
    flagged = _run(AgentRunStatus.RUNNING, cancel_requested_at=datetime.now(UTC))
    runs.get_or_404 = AsyncMock(return_value=flagged)
    cancelled = _run(AgentRunStatus.CANCELLED)
    runs.mark_cancelled_after_run = AsyncMock(return_value=cancelled)

    result = await service.fail_run(ORG_ID, AGENT_ID, error="boom")

    assert result.status is AgentRunStatus.CANCELLED
    runs.mark_failed.assert_not_called()
    runs.mark_cancelled_after_run.assert_awaited_once()


@pytest.mark.asyncio
async def test_fail_queued_run_fails() -> None:
    session, service, runs = _service()
    runs.get_or_404 = AsyncMock(return_value=_run(AgentRunStatus.QUEUED))
    failed = _run(AgentRunStatus.FAILED)
    runs.mark_failed_if_queued = AsyncMock(return_value=failed)

    result = await service.fail_queued_run(ORG_ID, AGENT_ID, error="agent offline")

    assert result.status is AgentRunStatus.FAILED
    runs.mark_failed_if_queued.assert_awaited_once()


# -- cancellation -----------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_queued_run_cancels_immediately() -> None:
    session, service, runs = _service()
    runs.get_or_404 = AsyncMock(return_value=_run(AgentRunStatus.QUEUED))
    cancelled = _run(AgentRunStatus.CANCELLED)
    runs.mark_cancelled_if_pending = AsyncMock(return_value=cancelled)

    result = await service.cancel_run(ORG_ID, AGENT_ID, cancelled_by_user_id=uuid.uuid4())

    assert result.status is AgentRunStatus.CANCELLED
    runs.mark_cancelled_if_pending.assert_awaited_once()
    assert session.committed is True


@pytest.mark.asyncio
async def test_cancel_running_run_requests_flag() -> None:
    session, service, runs = _service()
    runs.get_or_404 = AsyncMock(return_value=_run(AgentRunStatus.RUNNING))
    flagged = _run(AgentRunStatus.RUNNING, cancel_requested_at=datetime.now(UTC))
    runs.mark_cancel_requested = AsyncMock(return_value=flagged)

    result = await service.cancel_run(ORG_ID, AGENT_ID, cancelled_by_user_id=uuid.uuid4())

    assert result.status is AgentRunStatus.RUNNING
    assert result.cancel_requested_at is not None
    runs.mark_cancel_requested.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancel_already_cancelled_is_idempotent() -> None:
    session, service, runs = _service()
    runs.get_or_404 = AsyncMock(return_value=_run(AgentRunStatus.CANCELLED))

    result = await service.cancel_run(ORG_ID, AGENT_ID, cancelled_by_user_id=None)

    assert result.status is AgentRunStatus.CANCELLED
    runs.mark_cancel_requested.assert_not_called()
    runs.mark_cancelled_if_pending.assert_not_called()


@pytest.mark.asyncio
async def test_cancel_terminal_run_rejected_409() -> None:
    session, service, runs = _service()
    runs.get_or_404 = AsyncMock(return_value=_run(AgentRunStatus.SUCCEEDED))

    with pytest.raises(AppError) as exc:
        await service.cancel_run(ORG_ID, AGENT_ID, cancelled_by_user_id=None)
    assert exc.value.status_code == 409
    assert exc.value.code == "agent_run.not_cancellable"


@pytest.mark.asyncio
async def test_apply_cancel_cancels_flagged_running() -> None:
    session, service, runs = _service()
    flagged = _run(AgentRunStatus.RUNNING, cancel_requested_at=datetime.now(UTC))
    runs.get_or_404 = AsyncMock(return_value=flagged)
    cancelled = _run(AgentRunStatus.CANCELLED)
    runs.mark_cancelled_after_run = AsyncMock(return_value=cancelled)

    result = await service.apply_cancel(ORG_ID, AGENT_ID)

    assert result.status is AgentRunStatus.CANCELLED
    runs.mark_cancelled_after_run.assert_awaited_once()


# -- metadata-only updates --------------------------------------------------


@pytest.mark.asyncio
async def test_update_run_only_touches_metadata() -> None:
    session, service, runs = _service()
    run = _run(AgentRunStatus.RUNNING)
    runs.get_or_404 = AsyncMock(return_value=run)

    result = await service.update_run(
        ORG_ID, AGENT_ID, output={"partial": True}, duration_ms=1200
    )

    assert result is run
    assert result.status is AgentRunStatus.RUNNING
    assert result.output == {"partial": True}
    assert result.duration_ms == 1200
    assert session.committed is True
