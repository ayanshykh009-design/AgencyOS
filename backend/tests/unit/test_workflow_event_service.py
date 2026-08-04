"""Service-layer unit tests: workflow event publishing and trigger matching."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

from app.schemas.workflow_event import WorkflowEventCreate
from app.services.workflow_event_service import WorkflowEventService

ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
EVENT_ID = uuid.UUID("00000000-0000-0000-0000-000000000801")


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
    return service


def _event() -> WorkflowEventCreate:
    return WorkflowEventCreate(
        organization_id=ORG_ID, event_type="lead_created", payload={"lead_id": "x"}
    )


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
