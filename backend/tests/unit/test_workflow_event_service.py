"""Service-layer unit tests: workflow event publishing and trigger matching."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.errors import AppError
from app.core.metrics import read_counter, reset
from app.schemas.workflow_event import WorkflowEventCreate
from app.services.workflow_event_service import WorkflowEventService

ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
EVENT_ID = uuid.UUID("00000000-0000-0000-0000-000000000801")


@pytest.fixture(autouse=True)
def _reset_metrics() -> None:
    reset()


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0

    def add(self, obj: object) -> None:
        pass

    async def flush(self) -> None:
        pass

    async def refresh(self, obj: object) -> None:
        pass

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        pass


def _service() -> WorkflowEventService:
    service = WorkflowEventService(FakeSession())
    service._event_repo = MagicMock()
    service._event_repo.flush = AsyncMock()
    service._event_repo.refresh = AsyncMock()

    def _refresh(event: object) -> None:
        if getattr(event, "id", None) is None:
            event.id = EVENT_ID

    service._event_repo.refresh.side_effect = _refresh
    service._event_repo.add = MagicMock()
    service._trigger_repo = MagicMock()
    service._execution_service = MagicMock()
    service._automation_control = MagicMock()
    service._automation_control.block_queue_if_paused = AsyncMock()
    return service


def _event() -> WorkflowEventCreate:
    return WorkflowEventCreate(
        organization_id=ORG_ID, event_type="lead_created", payload={"lead_id": "x"}
    )


def _trigger() -> MagicMock:
    trigger = MagicMock(id=uuid.uuid4(), workflow_id=uuid.uuid4())
    trigger.config = {}
    trigger.enabled = True
    return trigger


async def _queue_executions(service: WorkflowEventService) -> None:
    async def _fake_queue(data: object, **kwargs: object) -> object:
        return MagicMock(id=uuid.uuid4())

    service._execution_service.queue = AsyncMock(side_effect=_fake_queue)


async def test_publish_with_matching_triggers_queues_executions_and_consumes() -> None:
    service = _service()
    events: list[object] = []
    service._event_repo.add.side_effect = lambda instance: events.append(instance)

    trigger_a = MagicMock(id=uuid.uuid4(), workflow_id=uuid.uuid4())
    trigger_b = MagicMock(id=uuid.uuid4(), workflow_id=uuid.uuid4())
    service._trigger_repo.get_by_event_type = AsyncMock(return_value=[trigger_a, trigger_b])

    async def _fake_queue(data: object, **kwargs: object) -> object:
        execution = MagicMock(id=uuid.uuid4())
        return execution

    service._execution_service.queue = AsyncMock(side_effect=_fake_queue)

    result = await service.publish(_event())

    assert result.consumed is True
    assert service._execution_service.queue.await_count == 2
    # The event row is marked consumed.
    event = events[0]
    assert event.consumed is True


async def test_publish_without_triggers_leaves_event_unconsumed() -> None:
    service = _service()
    events: list[object] = []
    service._event_repo.add.side_effect = lambda instance: events.append(instance)
    service._trigger_repo.get_by_event_type = AsyncMock(return_value=[])

    result = await service.publish(_event())

    assert result.consumed is False
    event = events[0]
    assert event.consumed is False


async def test_publish_commits_transaction() -> None:
    service = _service()
    service._trigger_repo.get_by_event_type = AsyncMock(return_value=[])

    await service.publish(_event())

    assert service._session.commits == 1


async def test_publish_passes_trigger_config_into_execution_input() -> None:
    service = _service()
    service._event_repo.add = MagicMock()
    trigger = MagicMock(id=uuid.uuid4(), workflow_id=uuid.uuid4())
    trigger.config = {"filter": {"industry": "saas"}}
    service._trigger_repo.get_by_event_type = AsyncMock(return_value=[trigger])

    captured: list[object] = []

    async def _fake_queue(data: object, **kwargs: object) -> object:
        captured.append(data)
        return MagicMock(id=uuid.uuid4())

    service._execution_service.queue = AsyncMock(side_effect=_fake_queue)

    await service.publish(_event())

    input_data = captured[0].input
    assert input_data["event"]["lead_id"] == "x"
    assert input_data["trigger_config"] == {"filter": {"industry": "saas"}}


async def test_list_and_count_delegate() -> None:
    service = _service()
    event = MagicMock(id=EVENT_ID)
    service._event_repo.list_by_org = AsyncMock(return_value=[event])
    service._event_repo.count_by_org = AsyncMock(return_value=1)

    assert await service.list_by_org(ORG_ID, event_type="lead_created") == [event]
    assert await service.count(ORG_ID, consumed=False) == 1


async def test_mark_consumed_scoped_to_org() -> None:
    service = _service()
    service._event_repo.mark_consumed = AsyncMock(return_value=1)
    event_ids = [EVENT_ID]

    result = await service.mark_consumed(ORG_ID, event_ids)

    assert result == 1
    service._event_repo.mark_consumed.assert_awaited_once()
    call_args = service._event_repo.mark_consumed.await_args.args
    assert call_args[0] == ORG_ID
    assert call_args[1] == event_ids


# --- Production guards -------------------------------------------------------


async def test_publish_blocks_when_automation_paused() -> None:
    service = _service()
    service._automation_control.block_queue_if_paused = AsyncMock(
        side_effect=AppError(
            code="automation.paused.queue_blocked",
            message="Automation is currently paused. New executions cannot be queued.",
            status_code=409,
        )
    )
    service._trigger_repo.get_by_event_type = AsyncMock(return_value=[])

    with pytest.raises(AppError) as exc_info:
        await service.publish(_event())

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "automation.paused.queue_blocked"
    service._event_repo.add.assert_not_called()
    service._trigger_repo.get_by_event_type.assert_not_awaited()
    assert read_counter("event_publish_total") == 0


async def test_publish_rejects_oversized_payload() -> None:
    service = _service()
    event = _event()
    event.payload = {"blob": "x" * 500}
    service._trigger_repo.get_by_event_type = AsyncMock(return_value=[])

    with pytest.raises(AppError) as exc_info:
        await service.publish(event, max_payload_bytes=100)

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "event.payload_too_large"
    service._trigger_repo.get_by_event_type.assert_not_awaited()
    assert read_counter("event_publish_total") == 0


async def test_publish_bounds_fanout_to_trigger_limit() -> None:
    service = _service()
    service._trigger_repo.get_by_event_type = AsyncMock(
        return_value=[_trigger() for _ in range(15)]
    )
    await _queue_executions(service)

    await service.publish(_event(), max_fanout=10)

    assert service._execution_service.queue.await_count == 10
    assert read_counter("event_fanout_truncated") == 1
    assert read_counter("event_executions_queued") == 10


async def test_publish_does_not_truncate_at_or_below_limit() -> None:
    service = _service()
    service._trigger_repo.get_by_event_type = AsyncMock(
        return_value=[_trigger() for _ in range(10)]
    )
    await _queue_executions(service)

    await service.publish(_event(), max_fanout=10)

    assert service._execution_service.queue.await_count == 10
    assert read_counter("event_fanout_truncated") == 0


async def test_publish_skips_disabled_triggers_within_limit() -> None:
    service = _service()
    triggers = [_trigger() for _ in range(3)]
    triggers[1].enabled = False
    service._trigger_repo.get_by_event_type = AsyncMock(return_value=triggers)
    await _queue_executions(service)

    await service.publish(_event(), max_fanout=10)

    assert service._execution_service.queue.await_count == 2
    assert read_counter("event_fanout_truncated") == 0


async def test_publish_queries_triggers_with_guarded_limit() -> None:
    service = _service()
    service._trigger_repo.get_by_event_type = AsyncMock(return_value=[])

    await service.publish(_event(), max_fanout=25)

    service._trigger_repo.get_by_event_type.assert_awaited_once_with(
        ORG_ID, "lead_created", limit=26
    )


# --- Fan-out load test -------------------------------------------------------


async def test_fan_out_load_single_event_to_many_triggers() -> None:
    """Publish one event against a large trigger set (capacity check).

    Asserts the publish path stays linear in the trigger count: exactly one
    trigger query and one queue call per trigger, with every queued execution
    carrying the event payload. This bounds the CPU/IO a single publish does.
    """
    trigger_count = 500
    service = _service()
    service._trigger_repo.get_by_event_type = AsyncMock(
        return_value=[_trigger() for _ in range(trigger_count)]
    )
    captured: list[object] = []

    async def _fake_queue(data: object, **kwargs: object) -> object:
        captured.append(data)
        return MagicMock(id=uuid.uuid4())

    service._execution_service.queue = AsyncMock(side_effect=_fake_queue)

    await service.publish(_event(), max_fanout=trigger_count)

    assert service._trigger_repo.get_by_event_type.await_count == 1
    assert service._execution_service.queue.await_count == trigger_count
    assert read_counter("event_executions_queued") == trigger_count
    assert read_counter("event_fanout_truncated") == 0
    assert all(c.input["event"] == {"lead_id": "x"} for c in captured)


async def test_fan_out_load_default_guard_caps_oversized_fan_out() -> None:
    """The configured default guard caps fan-out regardless of trigger count.

    With the default ``EVENT_FANOUT_MAX_TRIGGERS`` (100) and a far larger
    trigger set, publish truncates to the limit instead of queueing every
    trigger, so a misconfigured event_type can never flood the queue.
    """
    trigger_count = 500
    service = _service()
    service._trigger_repo.get_by_event_type = AsyncMock(
        return_value=[_trigger() for _ in range(trigger_count)]
    )
    await _queue_executions(service)

    await service.publish(_event())

    assert service._execution_service.queue.await_count <= 100
    assert read_counter("event_fanout_truncated") == 1
    assert read_counter("event_executions_queued") <= 100
