"""WorkflowEvent service: publish events, match triggers, queue executions."""
from __future__ import annotations

import json
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.core.metrics import get_counter
from app.models.workflow_event import WorkflowEvent
from app.repositories.workflow_event import WorkflowEventRepository
from app.repositories.workflow_trigger import WorkflowTriggerRepository
from app.schemas.workflow_event import WorkflowEventCreate
from app.schemas.workflow_execution import WorkflowExecutionCreate
from app.services.base import commit_with_retry, utcnow
from app.services.workflow_execution_service import WorkflowExecutionService

logger = logging.getLogger("agencyos.automation.event")


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

    async def publish(
        self,
        data: WorkflowEventCreate,
        *,
        max_fanout: int | None = None,
        max_payload_bytes: int | None = None,
    ) -> WorkflowEvent:
        """Publish an event and queue executions for matching triggers.

        Production guards: the serialized payload is capped (fail-fast 400
        before any write) and fan-out is bounded — at most ``max_fanout``
        triggers are queued per event. Exceeding either is misconfiguration
        and is surfaced via a counter + warning log rather than an unbounded
        transaction.
        """
        if data.organization_id is None:
            raise AppError(
                code="event.organization_required",
                message="organization_id is required",
                status_code=400,
            )
        if max_fanout is None:
            max_fanout = settings.EVENT_FANOUT_MAX_TRIGGERS
        if max_payload_bytes is None:
            max_payload_bytes = settings.EVENT_MAX_PAYLOAD_BYTES

        payload_size = len(
            json.dumps(data.payload, separators=(",", ":"), ensure_ascii=False)
        )
        if payload_size > max_payload_bytes:
            raise AppError(
                code="event.payload_too_large",
                message=f"Event payload exceeds the {max_payload_bytes} byte limit",
                status_code=400,
            )

        get_counter(
            "event_publish_total",
            description="Workflow events published",
        ).add()

        event = WorkflowEvent(
            organization_id=data.organization_id,
            event_type=data.event_type,
            payload=data.payload,
        )
        self._event_repo.add(event)
        await self._event_repo.flush()
        await self._event_repo.refresh(event)

        fetched = await self._trigger_repo.get_by_event_type(
            data.organization_id, data.event_type, limit=max_fanout + 1
        )
        truncated = len(fetched) > max_fanout
        triggers = fetched[:max_fanout]
        if truncated:
            get_counter(
                "event_fanout_truncated",
                description="Events whose fan-out exceeded the trigger limit",
            ).add()
            logger.warning(
                "event fan-out truncated: org=%s event_type=%s limit=%s",
                data.organization_id,
                data.event_type,
                max_fanout,
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
                get_counter(
                    "event_executions_queued",
                    description="Executions queued by workflow events",
                ).add()
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
