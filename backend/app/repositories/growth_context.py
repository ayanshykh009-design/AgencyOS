"""GrowthContext repository — read-only analytics snapshot assembly (M7).

Collects the org-scoped rows the deterministic growth engines consume into a
single :class:`GrowthContext`. Keeps engines pure (no DB access) and centralizes
the tenant-scoped, retention-aware reads in one place.

The analytics datatypes live in the service layer; they are imported lazily so
importing this repository never executes ``app.services`` (which would create
an import cycle through ``app.api.deps``).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log import ActivityLog
from app.models.growth_health_weight import GrowthHealthWeight
from app.models.growth_metric import GrowthMetric
from app.models.lead import Lead
from app.models.outreach_attempt import OutreachAttempt
from app.models.pipeline_stage import PipelineStage
from app.models.task import Task

if TYPE_CHECKING:
    from app.services.growth_analytics.datatypes import (
        ActivityPoint,
        AttemptPoint,
        GrowthContext,
        HealthWeightPoint,
        LeadPoint,
        MetricPoint,
        StagePoint,
        TaskPoint,
    )

_ACTIVE_OUTREACH_STATUSES = ("sent", "delivered", "manually_sent")
_REPLIED_OUTREACH_STATUSES = ("replied",)


class GrowthContextRepository:
    """Assembles org-scoped analytics snapshots for the M7 engines."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def build(
        self,
        organization_id: uuid.UUID,
        *,
        period_start: datetime,
        period_end: datetime,
    ) -> GrowthContext:
        """Load one analytics snapshot for the window."""
        from app.services.growth_analytics.datatypes import GrowthContext

        return GrowthContext(
            organization_id=organization_id,
            period_start=period_start,
            period_end=period_end,
            stages=await self._stages(organization_id),
            leads=await self._leads(organization_id),
            metrics=await self._metrics(organization_id, period_start, period_end),
            attempts=await self._attempts(organization_id, period_start, period_end),
            tasks=await self._tasks(organization_id, period_start, period_end),
            activity=await self._activity(organization_id, period_start, period_end),
            health_weights=await self._health_weights(organization_id),
        )

    async def _stages(self, organization_id: uuid.UUID) -> list[StagePoint]:
        from app.services.growth_analytics.datatypes import StagePoint

        stmt = (
            select(PipelineStage)
            .where(PipelineStage.organization_id == organization_id)
            .order_by(PipelineStage.position, PipelineStage.created_at)
        )
        result = await self._session.execute(stmt)
        return [
            StagePoint(
                id=stage.id,
                name=stage.name,
                position=stage.position,
                lifecycle=stage.lifecycle.value,
            )
            for stage in result.scalars().all()
        ]

    async def _leads(self, organization_id: uuid.UUID) -> list[LeadPoint]:
        from app.services.growth_analytics.datatypes import LeadPoint

        stmt = select(Lead).where(
            Lead.organization_id == organization_id,
            Lead.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return [
            LeadPoint(
                id=lead.id,
                status=lead.status.value,
                stage_id=lead.stage_id,
                deal_value=lead.deal_value,
                won_at=lead.won_at,
                lost_at=lead.lost_at,
                created_at=lead.created_at,
                owner_user_id=lead.owner_user_id,
                name=self._lead_name(lead),
            )
            for lead in result.scalars().all()
        ]

    @staticmethod
    def _lead_name(lead: Lead) -> str:
        """Human-readable lead name for opportunity snapshots."""
        parts = [part for part in (lead.first_name, lead.last_name) if part]
        return " ".join(parts).strip() or (lead.company or "")

    async def _metrics(
        self,
        organization_id: uuid.UUID,
        period_start: datetime,
        period_end: datetime,
    ) -> list[MetricPoint]:
        from app.services.growth_analytics.datatypes import MetricPoint

        stmt = select(GrowthMetric).where(
            GrowthMetric.organization_id == organization_id,
            GrowthMetric.period_start >= period_start,
            GrowthMetric.period_end <= period_end,
        )
        result = await self._session.execute(stmt)
        return [
            MetricPoint(
                metric_type=metric.metric_type,
                period_start=metric.period_start,
                period_end=metric.period_end,
                value=metric.value,
            )
            for metric in result.scalars().all()
        ]

    async def _attempts(
        self,
        organization_id: uuid.UUID,
        period_start: datetime,
        period_end: datetime,
    ) -> list[AttemptPoint]:
        from app.services.growth_analytics.datatypes import AttemptPoint

        stmt = select(OutreachAttempt).where(
            OutreachAttempt.organization_id == organization_id,
            OutreachAttempt.created_at >= period_start,
            OutreachAttempt.created_at <= period_end,
        )
        result = await self._session.execute(stmt)
        return [
            AttemptPoint(
                status=attempt.status.value,
                channel=attempt.channel.value if attempt.channel else "",
                created_at=attempt.created_at,
            )
            for attempt in result.scalars().all()
        ]

    async def _tasks(
        self,
        organization_id: uuid.UUID,
        period_start: datetime,
        period_end: datetime,
    ) -> list[TaskPoint]:
        from app.services.growth_analytics.datatypes import TaskPoint

        stmt = select(Task).where(
            Task.organization_id == organization_id,
            Task.created_at >= period_start,
            Task.created_at <= period_end,
        )
        result = await self._session.execute(stmt)
        return [
            TaskPoint(
                status=task.status.value if task.status else "",
                created_at=task.created_at,
                completed_at=task.completed_at,
            )
            for task in result.scalars().all()
        ]

    async def _activity(
        self,
        organization_id: uuid.UUID,
        period_start: datetime,
        period_end: datetime,
    ) -> list[ActivityPoint]:
        from app.services.growth_analytics.datatypes import ActivityPoint

        stmt = select(ActivityLog).where(
            ActivityLog.organization_id == organization_id,
            ActivityLog.created_at >= period_start,
            ActivityLog.created_at <= period_end,
        )
        result = await self._session.execute(stmt)
        return [
            ActivityPoint(
                event_type=event.event_type.value if event.event_type else "",
                created_at=event.created_at,
            )
            for event in result.scalars().all()
        ]

    async def _health_weights(self, organization_id: uuid.UUID) -> list[HealthWeightPoint]:
        """Flatten the active weight set into per-dimension points.

        ``growth_health_weights.weights`` is a JSONB dict of dimension -> weight;
        the partial unique index guarantees at most one active row per org.
        """
        from app.services.growth_analytics.datatypes import HealthWeightPoint

        stmt = (
            select(GrowthHealthWeight)
            .where(
                GrowthHealthWeight.organization_id == organization_id,
                GrowthHealthWeight.is_active.is_(True),
            )
            .order_by(GrowthHealthWeight.version.desc())
        )
        result = await self._session.execute(stmt)
        points: list[HealthWeightPoint] = []
        for row in result.scalars().all():
            for dimension, weight in (row.weights or {}).items():
                points.append(
                    HealthWeightPoint(
                        dimension=dimension,
                        weight=float(weight),
                        position=0,
                    )
                )
        return points

    @staticmethod
    def is_sent(status: str) -> bool:
        """Whether an outreach attempt status counts as successfully sent."""
        return status in _ACTIVE_OUTREACH_STATUSES

    @staticmethod
    def is_replied(status: str) -> bool:
        """Whether an outreach attempt status counts as replied."""
        return status in _REPLIED_OUTREACH_STATUSES
