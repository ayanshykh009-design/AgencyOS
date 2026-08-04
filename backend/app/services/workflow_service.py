"""Workflow service: CRUD, activation, and business rules."""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.activity_log import ActivityLog
from app.models.enums import ActivityEventType, WorkflowStatus
from app.models.workflow import Workflow
from app.repositories.activity_log import ActivityLogRepository
from app.repositories.workflow import WorkflowRepository
from app.schemas.workflow import WorkflowCreate, WorkflowUpdate
from app.schemas.workflow_trigger import WorkflowTriggerCreate, WorkflowTriggerUpdate
from app.services.base import commit_with_retry, utcnow
from app.services.workflow_trigger_service import WorkflowTriggerService

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.workflow_trigger import WorkflowTrigger


class WorkflowService:
    """Owns workflow business rules and the transaction boundary."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = WorkflowRepository(session)
        self._logs = ActivityLogRepository(session)
        self._trigger_service = WorkflowTriggerService(session)

    async def list_workflows(
        self,
        organization_id: uuid.UUID,
        *,
        status: WorkflowStatus | None = None,
        sort: str = "created_at",
        order: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> list[Workflow]:
        return await self._repo.list(
            organization_id,
            status=status,
            sort=sort,
            order=order,
            limit=limit,
            offset=offset,
        )

    async def count_workflows(
        self,
        organization_id: uuid.UUID,
        *,
        status: WorkflowStatus | None = None,
    ) -> int:
        return await self._repo.count(organization_id, status=status)

    async def list_active(self, organization_id: uuid.UUID) -> list[Workflow]:
        return await self._repo.list_active(organization_id)

    async def get_or_404(
        self, organization_id: uuid.UUID, workflow_id: uuid.UUID
    ) -> Workflow:
        return await self._repo.get_or_404(organization_id, workflow_id)

    async def create(
        self, data: WorkflowCreate, *, created_by_user_id: uuid.UUID
    ) -> Workflow:
        if data.organization_id is None:
            raise AppError(
                code="workflow.organization_required",
                message="organization_id is required",
                status_code=400,
            )

        workflow = Workflow(
            organization_id=data.organization_id,
            name=data.name,
            description=data.description,
            definition=data.definition,
            status=WorkflowStatus.DRAFT,
            version=1,
            execution_mode=data.execution_mode,
            config=data.config,
            created_by_user_id=created_by_user_id,
        )
        self._repo.add(workflow)
        self._logs.add(
            ActivityLog(
                organization_id=data.organization_id,
                user_id=created_by_user_id,
                event_type=ActivityEventType.WORKFLOW_CREATED,
                entity_type="workflow",
                entity_id=workflow.id,
                description=f"Created workflow '{workflow.name}'",
                metadata_={"name": workflow.name, "execution_mode": workflow.execution_mode},
                occurred_at=utcnow(),
            )
        )
        try:
            await self._repo.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise AppError(
                code="workflow.name_conflict",
                message="A workflow with that name already exists",
                status_code=409,
            ) from exc
        await commit_with_retry(self._session)
        return workflow

    async def update(
        self,
        organization_id: uuid.UUID,
        workflow_id: uuid.UUID,
        data: WorkflowUpdate,
        *,
        actor: User | None = None,
    ) -> Workflow:
        workflow = await self._repo.get_or_404(organization_id, workflow_id)

        if data.name is not None:
            workflow.name = data.name
        if data.description is not None:
            workflow.description = data.description
        if data.definition is not None:
            workflow.definition = data.definition
        if data.execution_mode is not None:
            workflow.execution_mode = data.execution_mode
        if data.config is not None:
            workflow.config = data.config
        if data.status is not None:
            workflow.status = data.status

        workflow.version += 1
        self._logs.add(
            ActivityLog(
                organization_id=organization_id,
                user_id=actor.id if actor else None,
                event_type=ActivityEventType.WORKFLOW_UPDATED,
                entity_type="workflow",
                entity_id=workflow.id,
                description=f"Updated workflow '{workflow.name}'",
                metadata_={"version": workflow.version},
                occurred_at=utcnow(),
            )
        )
        await commit_with_retry(self._session)
        return workflow

    async def activate(
        self,
        organization_id: uuid.UUID,
        workflow_id: uuid.UUID,
        *,
        actor: User | None = None,
    ) -> Workflow:
        workflow = await self._repo.get_or_404(organization_id, workflow_id)
        if workflow.status == WorkflowStatus.ACTIVE:
            raise AppError(
                code="workflow.already_active",
                message="Workflow is already active",
                status_code=400,
            )
        if workflow.status == WorkflowStatus.ARCHIVED:
            raise AppError(
                code="workflow.archived",
                message="Cannot activate an archived workflow",
                status_code=400,
            )
        workflow.status = WorkflowStatus.ACTIVE
        self._logs.add(
            ActivityLog(
                organization_id=organization_id,
                user_id=actor.id if actor else None,
                event_type=ActivityEventType.WORKFLOW_ACTIVATED,
                entity_type="workflow",
                entity_id=workflow.id,
                description=f"Activated workflow '{workflow.name}'",
                occurred_at=utcnow(),
            )
        )
        await commit_with_retry(self._session)
        return workflow

    async def pause(
        self,
        organization_id: uuid.UUID,
        workflow_id: uuid.UUID,
        *,
        actor: User | None = None,
    ) -> Workflow:
        workflow = await self._repo.get_or_404(organization_id, workflow_id)
        if workflow.status != WorkflowStatus.ACTIVE:
            raise AppError(
                code="workflow.not_active",
                message="Only active workflows can be paused",
                status_code=400,
            )
        workflow.status = WorkflowStatus.PAUSED
        self._logs.add(
            ActivityLog(
                organization_id=organization_id,
                user_id=actor.id if actor else None,
                event_type=ActivityEventType.WORKFLOW_PAUSED,
                entity_type="workflow",
                entity_id=workflow.id,
                description=f"Paused workflow '{workflow.name}'",
                occurred_at=utcnow(),
            )
        )
        await commit_with_retry(self._session)
        return workflow

    async def archive(
        self,
        organization_id: uuid.UUID,
        workflow_id: uuid.UUID,
        *,
        actor: User | None = None,
    ) -> Workflow:
        workflow = await self._repo.get_or_404(organization_id, workflow_id)
        if workflow.status == WorkflowStatus.ARCHIVED:
            raise AppError(
                code="workflow.already_archived",
                message="Workflow is already archived",
                status_code=400,
            )
        workflow.status = WorkflowStatus.ARCHIVED
        self._logs.add(
            ActivityLog(
                organization_id=organization_id,
                user_id=actor.id if actor else None,
                event_type=ActivityEventType.WORKFLOW_ARCHIVED,
                entity_type="workflow",
                entity_id=workflow.id,
                description=f"Archived workflow '{workflow.name}'",
                occurred_at=utcnow(),
            )
        )
        await commit_with_retry(self._session)
        return workflow

    async def delete(
        self,
        organization_id: uuid.UUID,
        workflow_id: uuid.UUID,
        *,
        actor: User | None = None,
    ) -> bool:
        workflow = await self._repo.get_or_404(organization_id, workflow_id)
        if workflow.status in (WorkflowStatus.ACTIVE, WorkflowStatus.PAUSED):
            raise AppError(
                code="workflow.active",
                message="Deactivate the workflow before deleting it",
                status_code=400,
            )
        result = await self._repo.delete(organization_id, workflow_id)
        self._logs.add(
            ActivityLog(
                organization_id=organization_id,
                user_id=actor.id if actor else None,
                event_type=ActivityEventType.WORKFLOW_DELETED,
                entity_type="workflow",
                entity_id=workflow_id,
                description=f"Deleted workflow '{workflow.name}'",
                occurred_at=utcnow(),
            )
        )
        await commit_with_retry(self._session)
        return result

    # Trigger delegation -------------------------------------------------------

    async def list_triggers(
        self,
        organization_id: uuid.UUID,
        *,
        workflow_id: uuid.UUID | None = None,
        trigger_type: str | None = None,
        enabled: bool | None = None,
        sort: str = "created_at",
        order: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> list[WorkflowTrigger]:
        return await self._trigger_service.list_triggers(
            organization_id,
            workflow_id=workflow_id,
            trigger_type=trigger_type,
            enabled=enabled,
            sort=sort,
            order=order,
            limit=limit,
            offset=offset,
        )

    async def count_triggers(
        self,
        organization_id: uuid.UUID,
        *,
        workflow_id: uuid.UUID | None = None,
        trigger_type: str | None = None,
        enabled: bool | None = None,
    ) -> int:
        return await self._trigger_service.count_triggers(
            organization_id,
            workflow_id=workflow_id,
            trigger_type=trigger_type,
            enabled=enabled,
        )

    async def create_trigger(
        self, organization_id: uuid.UUID, data: WorkflowTriggerCreate
    ) -> object:
        return await self._trigger_service.create(data)

    async def update_trigger(
        self,
        organization_id: uuid.UUID,
        trigger_id: uuid.UUID,
        data: WorkflowTriggerUpdate,
    ) -> object:
        return await self._trigger_service.update(organization_id, trigger_id, data)

    async def delete_trigger(
        self, organization_id: uuid.UUID, trigger_id: uuid.UUID
    ) -> None:
        await self._trigger_service.delete(organization_id, trigger_id)
