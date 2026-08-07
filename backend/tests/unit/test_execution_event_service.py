"""Unit tests: ExecutionEventService best-effort timeline writes."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

from app.models.enums import ExecutionEventType
from app.services.execution_event_service import ExecutionEventService

ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
WORKFLOW_ID = uuid.UUID("00000000-0000-0000-0000-000000000501")
EXECUTION_ID = uuid.UUID("00000000-0000-0000-0000-000000000601")


class FakeSavepoint:
    async def __aenter__(self) -> FakeSavepoint:
        return self

    async def __aexit__(self, *exc_info: object) -> bool:
        return False


class FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.flushed = False
        self.begin_nested_count = 0

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def add_all(self, objects: list[object]) -> None:
        self.added.extend(objects)

    async def flush(self) -> None:
        self.flushed = True

    def begin_nested(self) -> FakeSavepoint:
        self.begin_nested_count += 1
        return FakeSavepoint()


def _service(session: FakeSession | None = None) -> ExecutionEventService:
    service = ExecutionEventService(session or FakeSession())
    service._repo = MagicMock()
    service._repo.add = MagicMock()
    service._repo.add_all = MagicMock()
    service._repo.flush = AsyncMock()
    return service


async def test_record_appends_event_in_savepoint() -> None:
    session = FakeSession()
    service = _service(session)

    await service.record(
        organization_id=ORG_ID,
        workflow_id=WORKFLOW_ID,
        execution_id=EXECUTION_ID,
        attempt=2,
        event_type=ExecutionEventType.STEP_COMPLETED,
        metadata={"step_index": 1},
    )

    assert session.begin_nested_count == 1
    service._repo.add.assert_called_once()
    event = service._repo.add.call_args.args[0]
    assert event.organization_id == ORG_ID
    assert event.execution_id == EXECUTION_ID
    assert event.attempt == 2
    assert event.event_type == ExecutionEventType.STEP_COMPLETED
    assert event.metadata_ == {"step_index": 1}
    service._repo.flush.assert_awaited_once()


async def test_record_failure_is_best_effort() -> None:
    session = FakeSession()
    service = _service(session)
    service._repo.flush = AsyncMock(side_effect=RuntimeError("db down"))

    await service.record(
        organization_id=ORG_ID,
        workflow_id=WORKFLOW_ID,
        execution_id=EXECUTION_ID,
        attempt=1,
        event_type=ExecutionEventType.STARTED,
    )

    service._repo.flush.assert_awaited_once()
    assert session.begin_nested_count == 1


async def test_record_many_appends_all_events_in_one_savepoint() -> None:
    session = FakeSession()
    service = _service(session)
    events = [
        (ExecutionEventType.STEP_STARTED, {"step_index": 1, "step_id": "s1"}),
        (ExecutionEventType.STEP_COMPLETED, {"step_index": 1, "step_id": "s1"}),
    ]

    await service.record_many(
        organization_id=ORG_ID,
        workflow_id=WORKFLOW_ID,
        execution_id=EXECUTION_ID,
        attempt=1,
        events=events,
    )

    assert session.begin_nested_count == 1
    service._repo.add_all.assert_called_once()
    persisted = service._repo.add_all.call_args.args[0]
    assert [e.event_type for e in persisted] == [
        ExecutionEventType.STEP_STARTED,
        ExecutionEventType.STEP_COMPLETED,
    ]
    assert all(e.attempt == 1 for e in persisted)
    service._repo.flush.assert_awaited_once()


async def test_record_many_empty_list_is_noop() -> None:
    service = _service()

    await service.record_many(
        organization_id=ORG_ID,
        workflow_id=WORKFLOW_ID,
        execution_id=EXECUTION_ID,
        attempt=1,
        events=[],
    )

    service._repo.add_all.assert_not_called()
    service._repo.flush.assert_not_awaited()


async def test_record_many_failure_is_best_effort() -> None:
    session = FakeSession()
    service = _service(session)
    service._repo.flush = AsyncMock(side_effect=RuntimeError("db down"))

    await service.record_many(
        organization_id=ORG_ID,
        workflow_id=WORKFLOW_ID,
        execution_id=EXECUTION_ID,
        attempt=1,
        events=[(ExecutionEventType.STEP_STARTED, {"step_index": 1})],
    )

    service._repo.flush.assert_awaited_once()


async def test_list_and_count_delegate_with_pagination() -> None:
    service = _service()
    events = [MagicMock(), MagicMock()]
    service._repo.list_by_execution = AsyncMock(return_value=events)
    service._repo.count_by_execution = AsyncMock(return_value=2)

    listed = await service.list_by_execution(
        ORG_ID, EXECUTION_ID, limit=10, offset=20
    )
    count = await service.count_by_execution(ORG_ID, EXECUTION_ID)

    assert listed == events
    assert count == 2
    service._repo.list_by_execution.assert_awaited_once_with(
        ORG_ID, EXECUTION_ID, limit=10, offset=20
    )
    service._repo.count_by_execution.assert_awaited_once_with(ORG_ID, EXECUTION_ID)
