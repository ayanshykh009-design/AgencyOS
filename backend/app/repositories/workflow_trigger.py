"""WorkflowTrigger repository (org-scoped CRUD)."""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import WorkflowTriggerType
from app.models.workflow_trigger import WorkflowTrigger

if TYPE_CHECKING:
    pass


_DEFAULT_PAGE_SIZE = 50
_MAX_PAGE_SIZE = 200

# Module-level alias so ``list[...]`` annotations inside the class (which has a
# ``list`` method) resolve to the builtin type, not the shadowing method.
WorkflowTriggerList = list[WorkflowTrigger]


class WorkflowTriggerRepository:
    """Data access for workflow triggers."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self, organization_id: uuid.UUID, trigger_id: uuid.UUID
    ) -> WorkflowTrigger | None:
        stmt = select(WorkflowTrigger).where(
            WorkflowTrigger.organization_id == organization_id,
            WorkflowTrigger.id == trigger_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_404(
        self, organization_id: uuid.UUID, trigger_id: uuid.UUID
    ) -> WorkflowTrigger:
        from app.core.errors import AppError

        trigger = await self.get(organization_id, trigger_id)
        if trigger is None:
            raise AppError(
                code="workflow_trigger.not_found",
                message="Workflow trigger not found",
                status_code=404,
            )
        return trigger

    async def list(
        self,
        organization_id: uuid.UUID,
        *,
        workflow_id: uuid.UUID | None = None,
        trigger_type: WorkflowTriggerType | None = None,
        enabled: bool | None = None,
        sort: str = "created_at",
        order: str = "desc",
        limit: int = _DEFAULT_PAGE_SIZE,
        offset: int = 0,
    ) -> list[WorkflowTrigger]:
        stmt = select(WorkflowTrigger).where(WorkflowTrigger.organization_id == organization_id)
        if workflow_id is not None:
            stmt = stmt.where(WorkflowTrigger.workflow_id == workflow_id)
        if trigger_type is not None:
            stmt = stmt.where(WorkflowTrigger.trigger_type == trigger_type)
        if enabled is not None:
            stmt = stmt.where(WorkflowTrigger.enabled == enabled)

        sort_col = getattr(WorkflowTrigger, sort, WorkflowTrigger.created_at)
        if order == "desc":
            sort_col = sort_col.desc()
        stmt = stmt.order_by(sort_col).limit(min(limit, _MAX_PAGE_SIZE)).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(
        self,
        organization_id: uuid.UUID,
        *,
        workflow_id: uuid.UUID | None = None,
        trigger_type: WorkflowTriggerType | None = None,
        enabled: bool | None = None,
    ) -> int:
        stmt = (
            select(func.count(WorkflowTrigger.id))
            .where(WorkflowTrigger.organization_id == organization_id)
            .select_from(WorkflowTrigger)
        )
        if workflow_id is not None:
            stmt = stmt.where(WorkflowTrigger.workflow_id == workflow_id)
        if trigger_type is not None:
            stmt = stmt.where(WorkflowTrigger.trigger_type == trigger_type)
        if enabled is not None:
            stmt = stmt.where(WorkflowTrigger.enabled == enabled)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    def add(self, trigger: WorkflowTrigger) -> None:
        self._session.add(trigger)

    async def delete(self, organization_id: uuid.UUID, trigger_id: uuid.UUID) -> bool:
        trigger = await self.get(organization_id, trigger_id)
        if trigger is None:
            return False
        await self._session.delete(trigger)
        return True

    async def flush(self) -> None:
        await self._session.flush()

    async def refresh(self, trigger: WorkflowTrigger) -> None:
        await self._session.refresh(trigger)

    async def get_by_event_type(
        self, organization_id: uuid.UUID, event_type: str
    ) -> WorkflowTriggerList:
        """Return enabled event triggers matching an event type."""
        stmt = select(WorkflowTrigger).where(
            WorkflowTrigger.organization_id == organization_id,
            WorkflowTrigger.trigger_type == "event",
            WorkflowTrigger.event_type == event_type,
            WorkflowTrigger.enabled,
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_workflow(
        self, organization_id: uuid.UUID, workflow_id: uuid.UUID
    ) -> WorkflowTriggerList:
        stmt = (
            select(WorkflowTrigger)
            .where(
                WorkflowTrigger.organization_id == organization_id,
                WorkflowTrigger.workflow_id == workflow_id,
            )
            .order_by(WorkflowTrigger.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_all_by_org(self, organization_id: uuid.UUID) -> WorkflowTriggerList:
        stmt = (
            select(WorkflowTrigger)
            .where(WorkflowTrigger.organization_id == organization_id)
            .order_by(WorkflowTrigger.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_workflow(
        self, organization_id: uuid.UUID, workflow_id: uuid.UUID
    ) -> int:
        stmt = (
            select(func.count(WorkflowTrigger.id))
            .where(
                WorkflowTrigger.organization_id == organization_id,
                WorkflowTrigger.workflow_id == workflow_id,
            )
            .select_from(WorkflowTrigger)
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def count_all_by_org(self, organization_id: uuid.UUID) -> int:
        stmt = (
            select(func.count(WorkflowTrigger.id))
            .where(WorkflowTrigger.organization_id == organization_id)
            .select_from(WorkflowTrigger)
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())