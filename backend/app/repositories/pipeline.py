"""Repositories for pipeline stages and close reasons."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.close_reason import CloseReason
from app.models.enums import StageLifecycle
from app.models.pipeline_stage import PipelineStage


class PipelineStageRepository:
    """Data access for org-scoped pipeline stages."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, stage: PipelineStage) -> None:
        self._session.add(stage)

    async def delete(self, stage: PipelineStage) -> None:
        await self._session.delete(stage)

    async def get(
        self, organization_id: uuid.UUID, stage_id: uuid.UUID
    ) -> PipelineStage | None:
        stmt = select(PipelineStage).where(
            PipelineStage.organization_id == organization_id,
            PipelineStage.id == stage_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_404(
        self, organization_id: uuid.UUID, stage_id: uuid.UUID
    ) -> PipelineStage:
        stage = await self.get(organization_id, stage_id)
        if stage is None:
            raise AppError(
                code="pipeline.stage_not_found",
                message="Pipeline stage not found",
                status_code=404,
            )
        return stage

    async def list(
        self,
        organization_id: uuid.UUID,
        *,
        lifecycle: StageLifecycle | None = None,
    ) -> list[PipelineStage]:
        """Return stages ordered by position (then creation for ties)."""
        stmt = select(PipelineStage).where(
            PipelineStage.organization_id == organization_id
        )
        if lifecycle is not None:
            stmt = stmt.where(PipelineStage.lifecycle == lifecycle)
        stmt = stmt.order_by(PipelineStage.position, PipelineStage.created_at)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_default(
        self,
        organization_id: uuid.UUID,
        lifecycle: StageLifecycle,
        *,
        name_hint: str | None = None,
    ) -> PipelineStage | None:
        """Return the default stage for a lifecycle bucket.

        Prefers a stage whose name matches ``name_hint`` (used to keep a
        status-driven change aligned with a seeded stage), then the marked
        default, then the first stage in position order.
        """
        stages = await self.list(organization_id, lifecycle=lifecycle)
        if not stages:
            return None
        if name_hint:
            for stage in stages:
                if stage.name == name_hint:
                    return stage
        for stage in stages:
            if stage.is_default:
                return stage
        return stages[0]


class CloseReasonRepository:
    """Data access for org-scoped won/lost close reasons."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, reason: CloseReason) -> None:
        self._session.add(reason)

    async def delete(self, reason: CloseReason) -> None:
        await self._session.delete(reason)

    async def get(
        self, organization_id: uuid.UUID, close_reason_id: uuid.UUID
    ) -> CloseReason | None:
        stmt = select(CloseReason).where(
            CloseReason.organization_id == organization_id,
            CloseReason.id == close_reason_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_404(
        self, organization_id: uuid.UUID, close_reason_id: uuid.UUID
    ) -> CloseReason:
        reason = await self.get(organization_id, close_reason_id)
        if reason is None:
            raise AppError(
                code="pipeline.close_reason_not_found",
                message="Close reason not found",
                status_code=404,
            )
        return reason

    async def list(
        self,
        organization_id: uuid.UUID,
        *,
        lifecycle: StageLifecycle | None = None,
    ) -> list[CloseReason]:
        """Return close reasons (defaults first, then alphabetically)."""
        stmt = select(CloseReason).where(
            CloseReason.organization_id == organization_id
        )
        if lifecycle is not None:
            stmt = stmt.where(CloseReason.lifecycle == lifecycle)
        stmt = stmt.order_by(CloseReason.is_default.desc(), CloseReason.name)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
