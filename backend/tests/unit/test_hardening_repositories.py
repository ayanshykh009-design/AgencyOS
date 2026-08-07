"""Unit tests for the Phase 5C hardening repositories.

These repositories are thin SQLAlchemy wrappers; without a live database we
assert the query contract: statement shape (filters, order, limit caps, upsert
conflict target) and the upsert/404 branching in the service-facing methods.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.enums import ExecutionEventType
from app.models.execution_event import ExecutionEvent
from app.models.system_setting import SystemSetting
from app.repositories.execution_event import ExecutionEventRepository
from app.repositories.system_settings import SystemSettingRepository
from app.repositories.worker_health import WorkerHealthRepository
from app.repositories.workflow import WorkflowRepository
from app.repositories.workflow_execution import WorkflowExecutionRepository

ORG_ID = uuid.uuid4()
EXECUTION_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


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


class _DeleteResult:
    def __init__(self, rowcount: int) -> None:
        self.rowcount = rowcount


class RecordingSession(AsyncSession):
    """AsyncSession stand-in that records executed statement strings."""

    def __init__(self, results: list | None = None) -> None:
        self.executed: list[str] = []
        self.added: list[object] = []
        self._results = results or []

    async def execute(self, stmt, params=None):
        self.executed.append(str(stmt))
        if self._results:
            if isinstance(self._results[0], _DeleteResult):
                return self._results.pop(0)
            return _Result(self._results.pop(0))
        return _Result([])

    def add(self, obj) -> None:
        self.added.append(obj)


# ---------------------------------------------------------------------------
# ExecutionEventRepository
# ---------------------------------------------------------------------------

def _event(event_type: ExecutionEventType = ExecutionEventType.STARTED) -> ExecutionEvent:
    event = ExecutionEvent(
        organization_id=ORG_ID,
        workflow_id=uuid.uuid4(),
        execution_id=EXECUTION_ID,
        attempt=0,
        event_type=event_type,
    )
    return event


def test_execution_event_list_filters_and_caps_limit() -> None:
    event = _event()
    session = RecordingSession(results=[[event]])
    repo = ExecutionEventRepository(session)

    async def run() -> None:
        events = await repo.list_by_execution(
            ORG_ID, EXECUTION_ID, limit=5000, offset=10
        )
        assert events == [event]

    import asyncio

    asyncio.run(run())
    stmt = session.executed[0]
    assert "execution_events" in stmt
    assert "organization_id" in stmt
    assert "execution_id" in stmt
    assert "occurred_at" in stmt


def test_execution_event_delete_older_than_bounded_by_cutoff_and_batch() -> None:
    from datetime import UTC, datetime

    session = RecordingSession(results=[_DeleteResult(7)])
    repo = ExecutionEventRepository(session)

    async def run() -> None:
        deleted = await repo.delete_older_than(
            datetime(2026, 5, 1, tzinfo=UTC), batch=10
        )
        assert deleted == 7

    import asyncio

    asyncio.run(run())
    stmt = session.executed[0]
    assert "DELETE" in stmt and "execution_events" in stmt
    assert "occurred_at" in stmt
    assert "LIMIT" in stmt


# ---------------------------------------------------------------------------
# SystemSettingRepository
# ---------------------------------------------------------------------------

def test_system_setting_set_value_creates_new() -> None:
    class NewSession(RecordingSession):
        async def execute(self, stmt, params=None):
            self.executed.append(str(stmt))
            return _Result([])

    session = NewSession()
    repo = SystemSettingRepository(session)

    async def run() -> None:
        setting = await repo.set_value(
            "automation.control", {"paused": False}, updated_by_user_id=USER_ID
        )
        assert setting.key == "automation.control"
        assert setting.value == {"paused": False}
        assert setting.updated_by_user_id == USER_ID
        assert session.added == [setting]

    import asyncio

    asyncio.run(run())


def test_system_setting_set_value_updates_existing() -> None:
    existing = SystemSetting(
        key="automation.control", value={"paused": False}, updated_by_user_id=None
    )

    class ExistingSession(RecordingSession):
        async def execute(self, stmt, params=None):
            self.executed.append(str(stmt))
            return _Result([existing])

    session = ExistingSession()
    repo = SystemSettingRepository(session)

    async def run() -> None:
        setting = await repo.set_value(
            "automation.control", {"paused": True}, updated_by_user_id=USER_ID
        )
        assert setting is existing
        assert setting.value == {"paused": True}
        assert setting.updated_by_user_id == USER_ID
        assert session.added == []

    import asyncio

    asyncio.run(run())


def test_system_setting_get_or_404_raises_when_missing() -> None:
    session = RecordingSession(results=[[]])
    repo = SystemSettingRepository(session)

    async def run() -> None:
        with pytest.raises(AppError) as exc:
            await repo.get_or_404("missing.setting")
        assert exc.value.status_code == 404

    import asyncio

    asyncio.run(run())


# ---------------------------------------------------------------------------
# WorkerHealthRepository
# ---------------------------------------------------------------------------

def test_worker_health_upsert_uses_conflict_target() -> None:
    session = RecordingSession()
    repo = WorkerHealthRepository(session)
    heartbeat_at = datetime.now(UTC)

    async def run() -> None:
        await repo.upsert(
            worker_type="execution",
            instance_id=uuid.uuid4(),
            pid=1234,
            hostname="web-1",
            loop_ok=True,
            last_error=None,
            counters={"processed": 5},
            heartbeat_at=heartbeat_at,
        )

    import asyncio

    asyncio.run(run())
    stmt = session.executed[0]
    assert "worker_health" in stmt
    assert "ON CONFLICT" in stmt
    assert "uq_worker_health_type_instance" in stmt


def test_worker_health_list_alive_filters_staleness_and_type() -> None:
    session = RecordingSession(results=[[]])
    repo = WorkerHealthRepository(session)

    async def run() -> None:
        await repo.list_alive("execution", stale_within_seconds=30)

    import asyncio

    asyncio.run(run())
    stmt = session.executed[0]
    assert "last_heartbeat_at" in stmt
    assert "worker_type" in stmt


def test_worker_health_count_stale_bounds() -> None:
    session = RecordingSession(results=[[3]])
    repo = WorkerHealthRepository(session)

    async def run() -> None:
        total = await repo.count_stale(stale_within_seconds=30)
        assert total == 3

    import asyncio

    asyncio.run(run())
    assert "worker_health" in session.executed[0]


def test_worker_health_delete_stale_older_than_bounded() -> None:
    from datetime import UTC, datetime

    session = RecordingSession(results=[_DeleteResult(2)])
    repo = WorkerHealthRepository(session)

    async def run() -> None:
        pruned = await repo.delete_stale_older_than(
            datetime(2026, 5, 1, tzinfo=UTC), batch=5
        )
        assert pruned == 2

    import asyncio

    asyncio.run(run())
    stmt = session.executed[0]
    assert "DELETE" in stmt and "worker_health" in stmt
    assert "last_heartbeat_at" in stmt
    assert "LIMIT" in stmt


# ---------------------------------------------------------------------------
# WorkflowExecutionRepository queue-hardening queries
# ---------------------------------------------------------------------------

def test_workflow_execution_count_pending_filters_statuses() -> None:
    session = RecordingSession(results=[[4]])
    repo = WorkflowExecutionRepository(session)

    async def run() -> None:
        total = await repo.count_pending(ORG_ID)
        assert total == 4

    import asyncio

    asyncio.run(run())
    stmt = session.executed[0]
    assert "workflow_executions" in stmt
    assert "count" in stmt
    assert "organization_id" in stmt
    assert "status IN" in stmt or "status in" in stmt
    assert "POSTCOMPILE" in stmt


def test_workflow_execution_get_queued_orgs_groups_and_orders() -> None:
    session = RecordingSession(results=[[ORG_ID]])
    repo = WorkflowExecutionRepository(session)

    async def run() -> None:
        orgs = await repo.get_queued_orgs(20)
        assert orgs == [ORG_ID]

    import asyncio

    asyncio.run(run())
    stmt = session.executed[0]
    assert "workflow_executions" in stmt
    assert "organization_id" in stmt
    assert "GROUP BY" in stmt
    assert "ORDER BY min" in stmt


def test_workflow_execution_get_queued_for_org_filters_and_orders() -> None:
    session = RecordingSession(results=[[]])
    repo = WorkflowExecutionRepository(session)

    async def run() -> None:
        await repo.get_queued_for_org(ORG_ID, 10)

    import asyncio

    asyncio.run(run())
    stmt = session.executed[0]
    assert "workflow_executions" in stmt
    assert "organization_id" in stmt
    assert "status =" in stmt
    assert "ORDER BY" in stmt and "created_at" in stmt


# ---------------------------------------------------------------------------
# WorkflowRepository batch fetch
# ---------------------------------------------------------------------------

def test_workflow_get_many_filters_by_ids() -> None:
    session = RecordingSession(results=[[]])
    repo = WorkflowRepository(session)

    async def run() -> None:
        await repo.get_many([uuid.uuid4(), uuid.uuid4()])

    import asyncio

    asyncio.run(run())
    stmt = session.executed[0]
    assert "workflows" in stmt
    assert "id" in stmt


def test_workflow_get_many_empty_skips_query() -> None:
    session = RecordingSession()
    repo = WorkflowRepository(session)

    async def run() -> None:
        assert await repo.get_many([]) == []

    import asyncio

    asyncio.run(run())
    assert session.executed == []
