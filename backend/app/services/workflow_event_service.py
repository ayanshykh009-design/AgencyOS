"""WorkflowEvent service: publish events, match triggers, queue executions."""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.workflow_event import WorkflowEvent
from app.repositories.workflow_event import WorkflowEventRepository
from app.repositories.workflow_trigger import WorkflowTriggerRepository
from app.schemas.workflow_event import WorkflowEventCreate
from app.schemas.workflow_execution import WorkflowExecutionCreate
from app.services.base import commit_with_retry, utcnow
from app.services.workflow_execution_service import WorkflowExecutionService


class WorkflowEventService:
    """Owns event publishing and trigger matching."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._event_repo = WorkflowEventRepository(session)
        self._trigger_repo = WorkflowTriggerRepository(session)
        self._execution_service = WorkflowExecutionService(session)

    async def list_events(
        self,
        organization_id: uuid.UUID,
        *,
        event_type: str | None = None,
        consumed: bool | None = None,
        sort: str = "occurred_at",
        order: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> list[WorkflowEvent]:
        return await self._event_repo.list_by_org(
            organization_id,
            event_type=event_type,
            consumed=consumed,
            sort=sort,
            order=order,
            limit=limit,
            offset=offset,
        )

    async def count_events(
        self,
        organization_id: uuid.UUID,
        *,
        event_type: str | None = None,
        consumed: bool | None = None,
    ) -> int:
        return await self._event_repo.count_by_org(
            organization_id,
            event_type=event_type,
            consumed=consumed,
        )

    async def publish(self, data: WorkflowEventCreate) -> WorkflowEvent:
        """Publish an event and queue executions for matching triggers."""
        if data.organization_id is None:
            raise AppError(
                code="event.organization_required",
                message="organization_id is required",
                status_code=400,
            )

        event = WorkflowEvent(
            organization_id=data.organization_id,
            event_type=data.event_type,
            payload=data.payload,
        )
        self._event_repo.add(event)
        await self._event_repo.flush()
        await self._event_repo.refresh(event)

        triggers = await self._trigger_repo.get_by_event_type(
            data.organization_id, data.event_type
        )
        executions_queued = 0
        for trigger in triggers:
            if not trigger.enabled:
                continue
            try:
                await self._execution_service.queue(
                    WorkflowExecutionCreate(
                        organization_id=data.organization_id,
                        workflow_id=trigger.workflow_id,
                        trigger_id=trigger.id,
                        input={
                            "event": data.payload,
                            "trigger_config": trigger.config,
                        },
                    ),
                    requested_by_user_id=None,
                )
                executions_queued += 1
            except AppError:
                # Workflow missing/not active — skip this trigger, keep publishing.
                continue

        event.consumed = executions_queued > 0
        if event.consumed:
            event.consumed_at = utcnow()
        await commit_with_retry(self._session)
        return event

    async def list_by_org(
        self,
        organization_id: uuid.UUID,
        *,
        event_type: str | None = None,
        consumed: bool | None = None,
        sort: str = "occurred_at",
        order: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> list[WorkflowEvent]:
        return await self._event_repo.list_by_org(
            organization_id,
            event_type=event_type,
            consumed=consumed,
            sort=sort,
            order=order,
            limit=limit,
            offset=offset,
        )

    async def count(
        self,
        organization_id: uuid.UUID,
        *,
        event_type: str | None = None,
        consumed: bool | None = None,
    ) -> int:
        return await self._event_repo.count_by_org(
            organization_id,
            event_type=event_type,
            consumed=consumed,
        )

    async def mark_consumed(
        self, organization_id: uuid.UUID, event_ids: list[uuid.UUID]
    ) -> int:
        return await self._event_repo.mark_consumed(organization_id, event_ids)
