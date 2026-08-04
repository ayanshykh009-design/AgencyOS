"""WorkflowTrigger service: CRUD operations (delegated from WorkflowService)."""
from __future__ import annotations

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.enums import WorkflowTriggerType
from app.models.workflow_trigger import WorkflowTrigger
from app.repositories.workflow_trigger import WorkflowTriggerRepository
from app.schemas.workflow_trigger import WorkflowTriggerCreate, WorkflowTriggerUpdate
from app.services.base import commit_with_retry
from app.services.schedule_cron import validate_cron


class WorkflowTriggerService:
    """Owns workflow trigger business rules."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = WorkflowTriggerRepository(session)

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
        return await self._repo.list(
            organization_id,
            workflow_id=workflow_id,
            trigger_type=self._coerce_trigger_type(trigger_type),
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
        return await self._repo.count(
            organization_id,
            workflow_id=workflow_id,
            trigger_type=self._coerce_trigger_type(trigger_type),
            enabled=enabled,
        )

    @staticmethod
    def _coerce_trigger_type(value: str | None) -> WorkflowTriggerType | None:
        return WorkflowTriggerType(value) if value else None

    @staticmethod
    def _validate_schedule_cron(
        trigger_type: WorkflowTriggerType, schedule_cron: str | None
    ) -> None:
        """Validate schedule-trigger cron expressions (fail fast at write time)."""
        if trigger_type != WorkflowTriggerType.SCHEDULE:
            return
        if not schedule_cron:
            raise AppError(
                code="trigger.schedule_cron_required",
                message="schedule_cron is required for schedule triggers",
                status_code=400,
            )
        try:
            validate_cron(schedule_cron)
        except ValueError as exc:
            raise AppError(
                code="trigger.schedule_cron_invalid",
                message=f"Invalid cron expression: {exc}",
                status_code=400,
            ) from exc

    async def get_trigger(
        self, organization_id: uuid.UUID, trigger_id: uuid.UUID
    ) -> WorkflowTrigger:
        return await self._repo.get_or_404(organization_id, trigger_id)

    async def create(self, data: WorkflowTriggerCreate) -> WorkflowTrigger:
        if data.organization_id is None:
            raise AppError(
                code="workflow_trigger.organization_required",
                message="organization_id is required",
                status_code=400,
            )

        self._validate_schedule_cron(data.trigger_type, data.schedule_cron)
        if data.trigger_type == WorkflowTriggerType.EVENT and not data.event_type:
            raise AppError(
                code="trigger.event_type_required",
                message="event_type is required for event triggers",
                status_code=400,
            )
        if (
            data.trigger_type == WorkflowTriggerType.SCHEDULE
            and not data.schedule_cron
        ):
            raise AppError(
                code="trigger.schedule_cron_required",
                message="schedule_cron is required for schedule triggers",
                status_code=400,
            )

        trigger = WorkflowTrigger(
            organization_id=data.organization_id,
            workflow_id=data.workflow_id,
            name=data.name,
            trigger_type=data.trigger_type,
            event_type=data.event_type,
            schedule_cron=data.schedule_cron,
            config=data.config,
            enabled=data.enabled,
        )
        self._repo.add(trigger)
        try:
            await self._repo.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise AppError(
                code="workflow_trigger.create_failed",
                message="Could not create trigger",
                status_code=409,
            ) from exc
        await commit_with_retry(self._session)
        return trigger

    async def update(
        self,
        organization_id: uuid.UUID,
        trigger_id: uuid.UUID,
        data: WorkflowTriggerUpdate,
    ) -> WorkflowTrigger:
        trigger = await self._repo.get_or_404(organization_id, trigger_id)

        if data.name is not None:
            trigger.name = data.name
        if data.trigger_type is not None:
            trigger.trigger_type = data.trigger_type
        if data.event_type is not None:
            trigger.event_type = data.event_type
        if data.schedule_cron is not None:
            trigger.schedule_cron = data.schedule_cron
        if data.config is not None:
            trigger.config = data.config
        if data.enabled is not None:
            trigger.enabled = data.enabled

        self._validate_schedule_cron(trigger.trigger_type, trigger.schedule_cron)
        if trigger.trigger_type == WorkflowTriggerType.EVENT and not trigger.event_type:
            raise AppError(
                code="trigger.event_type_required",
                message="event_type is required for event triggers",
                status_code=400,
            )
        if (
            trigger.trigger_type == WorkflowTriggerType.SCHEDULE
            and not trigger.schedule_cron
        ):
            raise AppError(
                code="trigger.schedule_cron_required",
                message="schedule_cron is required for schedule triggers",
                status_code=400,
            )

        await commit_with_retry(self._session)
        return trigger

    async def delete(self, organization_id: uuid.UUID, trigger_id: uuid.UUID) -> bool:
        await self._repo.get_or_404(organization_id, trigger_id)
        return await self._repo.delete(organization_id, trigger_id)

    async def enable(
        self, organization_id: uuid.UUID, trigger_id: uuid.UUID
    ) -> WorkflowTrigger:
        return await self._set_enabled(organization_id, trigger_id, enabled=True)

    async def disable(
        self, organization_id: uuid.UUID, trigger_id: uuid.UUID
    ) -> WorkflowTrigger:
        return await self._set_enabled(organization_id, trigger_id, enabled=False)

    async def _set_enabled(
        self,
        organization_id: uuid.UUID,
        trigger_id: uuid.UUID,
        *,
        enabled: bool,
    ) -> WorkflowTrigger:
        trigger = await self._repo.get_or_404(organization_id, trigger_id)
        trigger.enabled = enabled
        await commit_with_retry(self._session)
        return trigger

    # Event-service delegation helpers ----------------------------------------

    async def list_by_workflow(
        self, organization_id: uuid.UUID, workflow_id: uuid.UUID
    ) -> list[WorkflowTrigger]:
        return await self._repo.list_by_workflow(organization_id, workflow_id)

    async def list_all_by_org(
        self, organization_id: uuid.UUID
    ) -> list[WorkflowTrigger]:
        return await self._repo.list_all_by_org(organization_id)

    async def count_by_workflow(
        self, organization_id: uuid.UUID, workflow_id: uuid.UUID
    ) -> int:
        return await self._repo.count_by_workflow(organization_id, workflow_id)

    async def count_all_by_org(self, organization_id: uuid.UUID) -> int:
        return await self._repo.count_all_by_org(organization_id)

    async def get_by_event_type(
        self, organization_id: uuid.UUID, event_type: str
    ) -> list[WorkflowTrigger]:
        return await self._repo.get_by_event_type(organization_id, event_type)
