"""ExecutionEvent service — append-only execution timeline writes.

Timeline events are *best-effort* by contract: a failure to persist an event
must never fail the execution transition it describes. Every ``record`` call
therefore writes inside its own savepoint; if the insert fails (constraint,
disk, whatever) only that savepoint rolls back and the surrounding transition
still commits. This keeps the execution state machine authoritative while the
timeline degrades gracefully under DB pressure.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ExecutionEventType
from app.models.execution_event import ExecutionEvent
from app.repositories.execution_event import ExecutionEventRepository
from app.services.base import utcnow

logger = logging.getLogger("agencyos.automation.timeline")


class ExecutionEventService:
    """Owns append-only timeline writes and pageable reads."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = ExecutionEventRepository(session)

    async def record(
        self,
        *,
        organization_id: uuid.UUID,
        workflow_id: uuid.UUID,
        execution_id: uuid.UUID,
        attempt: int,
        event_type: ExecutionEventType,
        metadata: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
    ) -> None:
        """Append one timeline event (best-effort, isolated savepoint)."""
        try:
            async with self._session.begin_nested():
                self._repo.add(
                    ExecutionEvent(
                        organization_id=organization_id,
                        workflow_id=workflow_id,
                        execution_id=execution_id,
                        attempt=attempt,
                        event_type=event_type,
                        metadata_=metadata or {},
                        occurred_at=occurred_at or utcnow(),
                    )
                )
                await self._repo.flush()
        except Exception:  # pragma: no cover - depends on DB failure
            logger.exception(
                "failed to record execution event execution_id=%s event=%s",
                execution_id,
                event_type,
            )

    async def record_many(
        self,
        *,
        organization_id: uuid.UUID,
        workflow_id: uuid.UUID,
        execution_id: uuid.UUID,
        attempt: int,
        events: list[tuple[ExecutionEventType, dict[str, Any]]],
        occurred_at: datetime | None = None,
    ) -> None:
        """Append several timeline events in one best-effort savepoint."""
        if not events:
            return
        try:
            async with self._session.begin_nested():
                base = occurred_at or utcnow()
                self._repo.add_all(
                    [
                        ExecutionEvent(
                            organization_id=organization_id,
                            workflow_id=workflow_id,
                            execution_id=execution_id,
                            attempt=attempt,
                            event_type=event_type,
                            metadata_=metadata,
                            occurred_at=base,
                        )
                        for event_type, metadata in events
                    ]
                )
                await self._repo.flush()
        except Exception:  # pragma: no cover - depends on DB failure
            logger.exception(
                "failed to record execution events execution_id=%s count=%s",
                execution_id,
                len(events),
            )

    async def list_by_execution(
        self,
        organization_id: uuid.UUID,
        execution_id: uuid.UUID,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ExecutionEvent]:
        return await self._repo.list_by_execution(
            organization_id, execution_id, limit=limit, offset=offset
        )

    async def count_by_execution(
        self, organization_id: uuid.UUID, execution_id: uuid.UUID
    ) -> int:
        return await self._repo.count_by_execution(organization_id, execution_id)
