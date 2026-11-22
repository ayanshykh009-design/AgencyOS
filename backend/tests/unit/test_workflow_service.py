"""Service-layer unit tests: workflow lifecycle (create/update/status)."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.errors import AppError
from app.models.enums import WorkflowStatus
from app.schemas.workflow import WorkflowCreate, WorkflowUpdate
from app.services.workflow_service import WorkflowService

ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000201")
WORKFLOW_ID = uuid.UUID("00000000-0000-0000-0000-000000000501")


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


def _service() -> WorkflowService:
    service = WorkflowService(FakeSession())
    service._repo = MagicMock()
    service._repo.flush = AsyncMock()
    service._repo.refresh = AsyncMock()
    service._repo.add = MagicMock()
    return service


def _create() -> WorkflowCreate:
    return WorkflowCreate(
        organization_id=ORG_ID,
        name="Lead enrichment",
        description="Enrich incoming leads",
        definition={"nodes": []},
        execution_mode="n8n",
        config={"webhook_path": "/webhook/enrich"},
    )


async def test_create_sets_draft_status() -> None:
    service = _service()
    created: list[object] = []
    service._repo.add.side_effect = lambda instance: created.append(instance)

    await service.create(_create(), created_by_user_id=USER_ID)

    instance = created[0]
    assert instance.organization_id == ORG_ID
    assert instance.status == WorkflowStatus.DRAFT
    assert instance.created_by_user_id == USER_ID


async def test_create_commits_transaction() -> None:
    service = _service()
    service._repo.add.side_effect = lambda instance: None

    await service.create(_create(), created_by_user_id=USER_ID)

    assert service._session.commits == 1


async def test_create_name_conflict_maps_to_409() -> None:
    service = _service()
    service._repo.flush = AsyncMock(side_effect=IntegrityError("", {}, Exception()))

    with pytest.raises(AppError) as exc_info:
        await service.create(_create(), created_by_user_id=USER_ID)

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "workflow.name_conflict"


async def test_create_rejects_invalid_builtin_definition() -> None:
    service = _service()
    data = WorkflowCreate(
        organization_id=ORG_ID,
        name="Builtin",
        execution_mode="builtin",
        definition={"steps": [{"type": "exec"}]},
    )

    with pytest.raises(AppError) as exc_info:
        await service.create(data, created_by_user_id=USER_ID)

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "workflow.builtin_definition_invalid"
    service._repo.flush.assert_not_awaited()


async def test_create_accepts_valid_builtin_definition() -> None:
    service = _service()
    service._repo.add.side_effect = lambda instance: None
    data = WorkflowCreate(
        organization_id=ORG_ID,
        name="Builtin",
        execution_mode="builtin",
        definition={
            "steps": [{"type": "set", "key": "greeting", "value": "Hi {{ input.name }}"}]
        },
    )

    await service.create(data, created_by_user_id=USER_ID)

    assert service._session.commits == 1


async def test_update_rejects_invalid_builtin_definition() -> None:
    service = _service()
    workflow = MagicMock()
    workflow.execution_mode = "builtin"
    workflow.definition = {"steps": [{"type": "unknown_step"}]}
    service._repo.get_or_404 = AsyncMock(return_value=workflow)

    with pytest.raises(AppError) as exc_info:
        await service.update(
            ORG_ID, WORKFLOW_ID, WorkflowUpdate(name="tweak")
        )

    assert exc_info.value.code == "workflow.builtin_definition_invalid"


async def test_update_validates_after_switching_mode_to_builtin() -> None:
    service = _service()
    workflow = MagicMock()
    workflow.execution_mode = "n8n"
    workflow.definition = {"steps": [{"type": "exec"}]}
    service._repo.get_or_404 = AsyncMock(return_value=workflow)

    with pytest.raises(AppError) as exc_info:
        await service.update(
            ORG_ID,
            WORKFLOW_ID,
            WorkflowUpdate(execution_mode="builtin"),
        )

    assert exc_info.value.code == "workflow.builtin_definition_invalid"


async def test_get_or_404_delegates_to_repo() -> None:
    service = _service()
    workflow = MagicMock()
    service._repo.get_or_404 = AsyncMock(return_value=workflow)

    result = await service.get_or_404(ORG_ID, WORKFLOW_ID)

    service._repo.get_or_404.assert_awaited_once_with(ORG_ID, WORKFLOW_ID)
    assert result is workflow


async def test_update_applies_only_provided_fields() -> None:
    service = _service()
    workflow = MagicMock()
    workflow.name = "old"
    workflow.description = "keep"
    workflow.status = WorkflowStatus.DRAFT
    service._repo.get_or_404 = AsyncMock(return_value=workflow)
    service._repo.flush = AsyncMock()
    service._repo.refresh = AsyncMock()

    result = await service.update(ORG_ID, WORKFLOW_ID, WorkflowUpdate(name="New name"))

    assert workflow.name == "New name"
    # Status is a lifecycle field and must never be touched by generic update.
    assert workflow.status == WorkflowStatus.DRAFT
    assert workflow.description == "keep"
    assert result is workflow


async def test_update_rejects_status_change() -> None:
    """B6-F-02: generic PATCH cannot bypass activate/pause/archive."""
    service = _service()
    workflow = MagicMock()
    workflow.name = "old"
    workflow.description = "keep"
    workflow.status = WorkflowStatus.DRAFT
    service._repo.get_or_404 = AsyncMock(return_value=workflow)

    with pytest.raises(AppError) as exc_info:
        await service.update(
            ORG_ID, WORKFLOW_ID, WorkflowUpdate(name="New name", status=WorkflowStatus.ACTIVE)
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "workflow.status_change_not_allowed"
    assert workflow.name == "old"
    assert workflow.status == WorkflowStatus.DRAFT
    assert service._session.commits == 0


async def test_create_trigger_uses_authenticated_organization() -> None:
    """B6-F-03: a client-supplied organization_id must never be trusted."""
    from app.models.enums import WorkflowTriggerType
    from app.schemas.workflow_trigger import WorkflowTriggerCreate

    service = _service()
    captured: list[WorkflowTriggerCreate] = []
    service._trigger_service = MagicMock()
    service._trigger_service.create = AsyncMock(
        side_effect=lambda data: (captured.append(data), data)[1]
    )
    foreign_org = uuid.UUID("00000000-0000-0000-0000-000000000099")
    data = WorkflowTriggerCreate(
        organization_id=foreign_org,
        workflow_id=WORKFLOW_ID,
        name="On lead created",
        trigger_type=WorkflowTriggerType.EVENT,
        event_type="lead_created",
    )

    await service.create_trigger(ORG_ID, data)

    assert len(captured) == 1
    assert captured[0].organization_id == ORG_ID
    assert data.organization_id == foreign_org  # caller's object is not mutated


async def test_nested_trigger_delegation_carries_path_workflow_id() -> None:
    """B6-F-03: nested routes must pass the path workflow to the trigger service."""
    service = _service()
    service._trigger_service = MagicMock()
    service._trigger_service.update = AsyncMock(return_value="updated")
    service._trigger_service.delete = AsyncMock(return_value=None)
    body = MagicMock()

    assert (
        await service.update_trigger(ORG_ID, WORKFLOW_ID, body, workflow_id=WORKFLOW_ID)
        == "updated"
    )
    service._trigger_service.update.assert_awaited_once_with(
        ORG_ID, WORKFLOW_ID, body, workflow_id=WORKFLOW_ID
    )

    await service.delete_trigger(ORG_ID, WORKFLOW_ID, workflow_id=WORKFLOW_ID)
    service._trigger_service.delete.assert_awaited_once_with(
        ORG_ID, WORKFLOW_ID, workflow_id=WORKFLOW_ID
    )


async def test_activate_rejects_archived() -> None:
    service = _service()
    workflow = MagicMock(status=WorkflowStatus.ARCHIVED)
    service._repo.get_or_404 = AsyncMock(return_value=workflow)

    with pytest.raises(AppError) as exc_info:
        await service.activate(ORG_ID, WORKFLOW_ID)

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "workflow.archived"


async def test_activate_sets_active() -> None:
    service = _service()
    workflow = MagicMock(status=WorkflowStatus.DRAFT)
    service._repo.get_or_404 = AsyncMock(return_value=workflow)

    await service.activate(ORG_ID, WORKFLOW_ID)

    assert workflow.status == WorkflowStatus.ACTIVE


async def test_pause_and_archive() -> None:
    service = _service()
    workflow = MagicMock(status=WorkflowStatus.ACTIVE)
    service._repo.get_or_404 = AsyncMock(return_value=workflow)

    await service.pause(ORG_ID, WORKFLOW_ID)
    assert workflow.status == WorkflowStatus.PAUSED

    await service.archive(ORG_ID, WORKFLOW_ID)
    assert workflow.status == WorkflowStatus.ARCHIVED


async def test_delete_rejects_active_or_paused() -> None:
    for status in (WorkflowStatus.ACTIVE, WorkflowStatus.PAUSED):
        service = _service()
        workflow = MagicMock(status=status)
        service._repo.get_or_404 = AsyncMock(return_value=workflow)

        with pytest.raises(AppError) as exc_info:
            await service.delete(ORG_ID, WORKFLOW_ID)

        assert exc_info.value.code == "workflow.active"


async def test_delete_allowed_for_draft() -> None:
    service = _service()
    workflow = MagicMock(status=WorkflowStatus.DRAFT)
    service._repo.get_or_404 = AsyncMock(return_value=workflow)
    service._repo.delete = AsyncMock(return_value=True)

    result = await service.delete(ORG_ID, WORKFLOW_ID)

    assert result is True
    service._repo.delete.assert_awaited_once_with(ORG_ID, WORKFLOW_ID)
