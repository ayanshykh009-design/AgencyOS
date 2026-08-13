"""Workflow repository (org-scoped CRUD)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import WorkflowStatus
from app.models.workflow import Workflow

if TYPE_CHECKING:
    pass


_DEFAULT_PAGE_SIZE = 50
_MAX_PAGE_SIZE = 200

# Module-level alias so ``list[...]`` annotations inside the class (which has a
# ``list`` method) resolve to the builtin type, not the shadowing method.
WorkflowList = list[Workflow]


class WorkflowRepository:
    """Data access for workflows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, organization_id: uuid.UUID, workflow_id: uuid.UUID) -> Workflow | None:
        stmt = select(Workflow).where(
            Workflow.organization_id == organization_id,
            Workflow.id == workflow_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_many(self, workflow_ids: list[uuid.UUID]) -> list[Workflow]:
        """Batch-fetch workflows by id (worker drain avoids a per-row query)."""
        if not workflow_ids:
            return []
        stmt = select(Workflow).where(Workflow.id.in_(workflow_ids))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_or_404(self, organization_id: uuid.UUID, workflow_id: uuid.UUID) -> Workflow:
        from app.core.errors import AppError

        workflow = await self.get(organization_id, workflow_id)
        if workflow is None:
            raise AppError(
                code="workflow.not_found",
                message="Workflow not found",
                status_code=404,
            )
        return workflow

    async def list(
        self,
        organization_id: uuid.UUID,
        *,
        status: WorkflowStatus | None = None,
        sort: str = "created_at",
        order: str = "desc",
        limit: int = _DEFAULT_PAGE_SIZE,
        offset: int = 0,
    ) -> list[Workflow]:
        stmt = select(Workflow).where(Workflow.organization_id == organization_id)
        if status is not None:
            stmt = stmt.where(Workflow.status == status)

        sort_col = getattr(Workflow, sort, Workflow.created_at)
        if order == "desc":
            sort_col = sort_col.desc()
        stmt = stmt.order_by(sort_col).limit(min(limit, _MAX_PAGE_SIZE)).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(
        self,
        organization_id: uuid.UUID,
        *,
        status: WorkflowStatus | None = None,
    ) -> int:
        stmt = (
            select(func.count(Workflow.id))
            .where(Workflow.organization_id == organization_id)
            .select_from(Workflow)
        )
        if status is not None:
            stmt = stmt.where(Workflow.status == status)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def list_active(self, organization_id: uuid.UUID) -> WorkflowList:
        """Return all active workflows for an organization (newest first)."""
        stmt = (
            select(Workflow)
            .where(
                Workflow.organization_id == organization_id,
                Workflow.status == WorkflowStatus.ACTIVE,
            )
            .order_by(Workflow.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    def add(self, workflow: Workflow) -> None:
        self._session.add(workflow)

    async def delete(self, organization_id: uuid.UUID, workflow_id: uuid.UUID) -> bool:
        workflow = await self.get(organization_id, workflow_id)
        if workflow is None:
            return False
        await self._session.delete(workflow)
        return True

    async def flush(self) -> None:
        await self._session.flush()

    async def refresh(self, workflow: Workflow) -> None:
        await self._session.refresh(workflow)
