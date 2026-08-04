"""Service-layer unit tests: workflow triggers (CRUD + per-type validation)."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.errors import AppError
from app.models.enums import WorkflowTriggerType
from app.schemas.workflow_trigger import WorkflowTriggerCreate, WorkflowTriggerUpdate
from app.services.workflow_trigger_service import WorkflowTriggerService

ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
WORKFLOW_ID = uuid.UUID("00000000-0000-0000-0000-000000000501")
TRIGGER_ID = uuid.UUID("00000000-0000-0000-0000-000000000701")


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


def _service() -> WorkflowTriggerService:
    service = WorkflowTriggerService(FakeSession())
    service._repo = MagicMock()
    service._repo.flush = AsyncMock()
    service._repo.refresh = AsyncMock()
    service._repo.add = MagicMock()
    return service


def _create(event_type: str | None = "lead_created") -> WorkflowTriggerCreate:
    return WorkflowTriggerCreate(
        organization_id=ORG_ID,
        workflow_id=WORKFLOW_ID,
        name="On lead created",
        trigger_type=WorkflowTriggerType.EVENT,
        event_type=event_type,
        schedule_cron=None,
        config={},
        enabled=True,
    )


async def test_create_builds_trigger() -> None:
    service = _service()
    created: list[object] = []
    service._repo.add.side_effect = lambda instance: created.append(instance)

    await service.create(_create())

    instance = created[0]
    assert instance.organization_id == ORG_ID
    assert instance.workflow_id == WORKFLOW_ID
    assert instance.trigger_type == WorkflowTriggerType.EVENT
    assert instance.event_type == "lead_created"
    assert instance.enabled is True


async def test_create_commits_transaction() -> None:
    service = _service()

    await service.create(_create())

    assert service._session.commits == 1


async def test_update_requires_event_type_for_event_triggers() -> None:
    service = _service()
    trigger = MagicMock()
    trigger.trigger_type = WorkflowTriggerType.MANUAL
    trigger.event_type = None
    trigger.schedule_cron = None
    service._repo.get_or_404 = AsyncMock(return_value=trigger)

    with pytest.raises(AppError) as exc_info:
        await service.update(
            ORG_ID,
            TRIGGER_ID,
            WorkflowTriggerUpdate(trigger_type=WorkflowTriggerType.EVENT),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "trigger.event_type_required"


async def test_update_requires_schedule_cron_for_schedule_triggers() -> None:
    service = _service()
    trigger = MagicMock()
    trigger.trigger_type = WorkflowTriggerType.MANUAL
    trigger.event_type = None
    trigger.schedule_cron = None
    service._repo.get_or_404 = AsyncMock(return_value=trigger)

    with pytest.raises(AppError) as exc_info:
        await service.update(
            ORG_ID,
            TRIGGER_ID,
            WorkflowTriggerUpdate(trigger_type=WorkflowTriggerType.SCHEDULE),
        )

    assert exc_info.value.code == "trigger.schedule_cron_required"


async def test_create_rejects_invalid_schedule_cron() -> None:
    service = _service()

    with pytest.raises(AppError) as exc_info:
        await service.create(
            WorkflowTriggerCreate(
                organization_id=ORG_ID,
                workflow_id=WORKFLOW_ID,
                name="Bad cron",
                trigger_type=WorkflowTriggerType.SCHEDULE,
                schedule_cron="99 99 * * *",
                enabled=True,
            )
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "trigger.schedule_cron_invalid"


async def test_update_rejects_invalid_schedule_cron() -> None:
    service = _service()
    trigger = MagicMock()
    trigger.trigger_type = WorkflowTriggerType.SCHEDULE
    trigger.event_type = None
    trigger.schedule_cron = "not-a-cron"
    service._repo.get_or_404 = AsyncMock(return_value=trigger)

    with pytest.raises(AppError) as exc_info:
        await service.update(ORG_ID, TRIGGER_ID, WorkflowTriggerUpdate(enabled=True))

    assert exc_info.value.code == "trigger.schedule_cron_invalid"


async def test_update_applies_fields() -> None:
    service = _service()
    trigger = MagicMock()
    trigger.trigger_type = WorkflowTriggerType.MANUAL
    trigger.event_type = None
    trigger.schedule_cron = None
    trigger.enabled = True
    service._repo.get_or_404 = AsyncMock(return_value=trigger)

    result = await service.update(ORG_ID, TRIGGER_ID, WorkflowTriggerUpdate(enabled=False))

    assert trigger.enabled is False
    assert result is trigger


async def test_enable_disable() -> None:
    service = _service()
    trigger = MagicMock(enabled=False)
    service._repo.get_or_404 = AsyncMock(return_value=trigger)

    await service.enable(ORG_ID, TRIGGER_ID)
    assert trigger.enabled is True

    await service.disable(ORG_ID, TRIGGER_ID)
    assert trigger.enabled is False


async def test_listing_delegates() -> None:
    service = _service()
    triggers = [MagicMock()]
    service._repo.list_by_workflow = AsyncMock(return_value=triggers)
    service._repo.list_all_by_org = AsyncMock(return_value=triggers)
    service._repo.count_by_workflow = AsyncMock(return_value=1)
    service._repo.count_all_by_org = AsyncMock(return_value=1)
    service._repo.get_by_event_type = AsyncMock(return_value=triggers)

    assert await service.list_by_workflow(ORG_ID, WORKFLOW_ID) == triggers
    assert await service.list_all_by_org(ORG_ID) == triggers
    assert await service.count_by_workflow(ORG_ID, WORKFLOW_ID) == 1
    assert await service.count_all_by_org(ORG_ID) == 1
    assert await service.get_by_event_type(ORG_ID, "lead_created") == triggers
