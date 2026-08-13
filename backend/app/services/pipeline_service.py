"""Pipeline service: stages, close reasons, and stage transitions.

The pipeline is an overlay on the fixed ``lead_status`` lifecycle:
  * seeded stages mirror the open statuses plus ``won``/``lost``;
  * moving a lead onto a stage whose lifecycle is ``won``/``lost`` drives
    ``leads.status``, timestamps, and close-reason bookkeeping;
  * ``leads.stage_id`` is the Kanban column; ``leads.status`` stays the
    coarse funnel marker consumed by the existing dashboard contracts.

All status/stage/close-reason transitions flow through :meth:`reconcile`,
which is the single source of truth for win/loss events.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.activity_log import ActivityLog
from app.models.close_reason import CloseReason
from app.models.enums import ActivityEventType, LeadStatus, StageLifecycle
from app.models.lead import Lead
from app.models.pipeline_stage import PipelineStage
from app.models.user import User
from app.repositories.activity_log import ActivityLogRepository
from app.repositories.lead import LeadRepository
from app.repositories.pipeline import CloseReasonRepository, PipelineStageRepository
from app.services.base import commit_with_retry, utcnow

_OPEN_STATUSES = {
    LeadStatus.NEW,
    LeadStatus.RESEARCHING,
    LeadStatus.CONTACTED,
    LeadStatus.MEETING_BOOKED,
    LeadStatus.PROPOSAL_SENT,
}

_LIFECYCLE_ORDER = {
    StageLifecycle.OPEN: 0,
    StageLifecycle.WON: 1,
    StageLifecycle.LOST: 2,
}

# Seeded stages mirror the lead_status lifecycle (position = board order).
_DEFAULT_STAGES: tuple[tuple[str, StageLifecycle, bool], ...] = (
    ("new", StageLifecycle.OPEN, True),
    ("researching", StageLifecycle.OPEN, False),
    ("contacted", StageLifecycle.OPEN, False),
    ("meeting_booked", StageLifecycle.OPEN, False),
    ("proposal_sent", StageLifecycle.OPEN, False),
    ("won", StageLifecycle.WON, True),
    ("lost", StageLifecycle.LOST, True),
)

_DEFAULT_CLOSE_REASONS: tuple[tuple[str, StageLifecycle, bool], ...] = (
    ("Contract signed", StageLifecycle.WON, True),
    ("Budget", StageLifecycle.LOST, True),
    ("Not a fit", StageLifecycle.LOST, False),
    ("No response", StageLifecycle.LOST, False),
)


def bucket_of(status: LeadStatus) -> StageLifecycle:
    """Map a lead status to its coarse pipeline bucket."""
    if status is LeadStatus.WON:
        return StageLifecycle.WON
    if status is LeadStatus.LOST:
        return StageLifecycle.LOST
    return StageLifecycle.OPEN


def open_status_for(stage: PipelineStage, previous: LeadStatus) -> LeadStatus:
    """Pick an open status for a lead sitting in an open stage.

    Uses the seeded status name when the stage maps to one; otherwise keeps
    the previous open status, falling back to ``contacted`` (generic active).
    """
    try:
        candidate = LeadStatus(stage.name)
    except ValueError:
        candidate = None
    if candidate in _OPEN_STATUSES:
        return candidate
    if previous in _OPEN_STATUSES:
        return previous
    return LeadStatus.CONTACTED


class PipelineService:
    """Owns pipeline business rules and the transaction boundary."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._stages = PipelineStageRepository(session)
        self._reasons = CloseReasonRepository(session)
        self._leads = LeadRepository(session)
        self._activity = ActivityLogRepository(session)

    # -- reads ----------------------------------------------------------

    async def list_stages(self, organization_id: uuid.UUID) -> list[PipelineStage]:
        await self._ensure_defaults(organization_id)
        await commit_with_retry(self._session)
        return await self._stages.list(organization_id)

    async def stage_counts(self, organization_id: uuid.UUID) -> dict[uuid.UUID, int]:
        return await self._leads.count_by_stage(organization_id)

    async def board(
        self,
        organization_id: uuid.UUID,
        *,
        limit_per_stage: int = 50,
    ) -> list[tuple[PipelineStage, list[Lead]]]:
        """Return (stage, leads) columns ordered open → won → lost."""
        await self._ensure_defaults(organization_id)
        await commit_with_retry(self._session)
        stages = await self._stages.list(organization_id)
        stages.sort(key=lambda s: (_LIFECYCLE_ORDER[s.lifecycle], s.position, str(s.id)))
        by_stage = await self._leads.list_by_stages(
            organization_id, [s.id for s in stages], limit_per_stage=limit_per_stage
        )
        return [(s, by_stage.get(s.id, [])) for s in stages]

    async def list_close_reasons(
        self,
        organization_id: uuid.UUID,
        *,
        lifecycle: StageLifecycle | None = None,
    ) -> list[CloseReason]:
        await self._ensure_defaults(organization_id)
        await commit_with_retry(self._session)
        return await self._reasons.list(organization_id, lifecycle=lifecycle)

    # -- stage management (admin) ---------------------------------------

    async def create_stage(
        self,
        organization_id: uuid.UUID,
        actor: User,
        *,
        name: str,
        lifecycle: StageLifecycle,
        position: int | None = None,
    ) -> PipelineStage:
        name = name.strip()
        if not name:
            raise AppError(
                code="pipeline.stage_name_required",
                message="Stage name is required",
                status_code=400,
            )
        stages = await self._stages.list(organization_id)
        if any(s.name == name and s.lifecycle is lifecycle for s in stages):
            raise AppError(
                code="pipeline.stage_exists",
                message="A stage with that name already exists in this lifecycle",
                status_code=409,
            )
        if position is None:
            position = max((s.position for s in stages), default=-1) + 1
        stage = PipelineStage(
            organization_id=organization_id,
            name=name,
            lifecycle=lifecycle,
            position=position,
            is_default=False,
        )
        self._stages.add(stage)
        await commit_with_retry(self._session)
        return stage

    async def update_stage(
        self,
        organization_id: uuid.UUID,
        stage_id: uuid.UUID,
        *,
        name: str | None = None,
        position: int | None = None,
    ) -> PipelineStage:
        stage = await self._stages.get_or_404(organization_id, stage_id)
        if name is not None:
            name = name.strip()
            if not name:
                raise AppError(
                    code="pipeline.stage_name_required",
                    message="Stage name is required",
                    status_code=400,
                )
            stage.name = name
        if position is not None:
            stage.position = position
        await commit_with_retry(self._session)
        return stage

    async def delete_stage(self, organization_id: uuid.UUID, stage_id: uuid.UUID) -> None:
        stage = await self._stages.get_or_404(organization_id, stage_id)
        alternatives = [
            s
            for s in await self._stages.list(organization_id, lifecycle=stage.lifecycle)
            if s.id != stage.id
        ]
        in_stage = await self._leads.count_in_stage(organization_id, stage.id)
        if in_stage and not alternatives:
            raise AppError(
                code="pipeline.no_alternative_stage",
                message=(
                    "This stage still contains leads and no alternative stage "
                    "exists in the same lifecycle"
                ),
                status_code=400,
            )
        if in_stage:
            await self._leads.bulk_move_stage(organization_id, stage.id, alternatives[0].id)
        await self._stages.delete(stage)
        await commit_with_retry(self._session)

    async def reorder_stages(
        self, organization_id: uuid.UUID, stage_ids: list[uuid.UUID]
    ) -> list[PipelineStage]:
        stages = await self._stages.list(organization_id)
        if set(stage_ids) != {s.id for s in stages} or len(stage_ids) != len(stages):
            raise AppError(
                code="pipeline.stage_reorder_mismatch",
                message="Reorder payload must include every stage exactly once",
                status_code=400,
            )
        by_id = {s.id: s for s in stages}
        for position, stage_id in enumerate(stage_ids):
            by_id[stage_id].position = position
        await commit_with_retry(self._session)
        return await self._stages.list(organization_id)

    # -- close reasons (admin) ------------------------------------------

    async def create_close_reason(
        self,
        organization_id: uuid.UUID,
        actor: User,
        *,
        name: str,
        lifecycle: StageLifecycle,
    ) -> CloseReason:
        name = name.strip()
        if not name:
            raise AppError(
                code="pipeline.close_reason_name_required",
                message="Close reason name is required",
                status_code=400,
            )
        if lifecycle is StageLifecycle.OPEN:
            raise AppError(
                code="pipeline.close_reason_invalid_lifecycle",
                message="Close reasons apply only to won/lost stages",
                status_code=400,
            )
        existing = await self._reasons.list(organization_id, lifecycle=lifecycle)
        if any(r.name == name for r in existing):
            raise AppError(
                code="pipeline.close_reason_exists",
                message="A close reason with that name already exists",
                status_code=409,
            )
        reason = CloseReason(
            organization_id=organization_id,
            lifecycle=lifecycle,
            name=name,
            is_default=False,
        )
        self._reasons.add(reason)
        await commit_with_retry(self._session)
        return reason

    async def delete_close_reason(
        self, organization_id: uuid.UUID, close_reason_id: uuid.UUID
    ) -> None:
        reason = await self._reasons.get_or_404(organization_id, close_reason_id)
        used = await self._leads.count_using_close_reason(organization_id, close_reason_id)
        if used:
            raise AppError(
                code="pipeline.close_reason_in_use",
                message="This close reason is still used by active leads",
                status_code=409,
            )
        await self._reasons.delete(reason)
        await commit_with_retry(self._session)

    # -- transitions -----------------------------------------------------

    async def move(
        self,
        organization_id: uuid.UUID,
        actor: User,
        lead: Lead,
        *,
        stage_id: uuid.UUID,
        close_reason_id: uuid.UUID | None = None,
    ) -> Lead:
        """Move a lead onto a stage; drives status/timestamps/events."""
        await self.reconcile(
            organization_id,
            lead,
            stage_id=stage_id,
            close_reason_id=close_reason_id,
            actor=actor,
            emit_events=True,
        )
        await commit_with_retry(self._session)
        return lead

    async def reconcile(
        self,
        organization_id: uuid.UUID,
        lead: Lead,
        *,
        status: LeadStatus | None = None,
        stage_id: uuid.UUID | None = None,
        close_reason_id: uuid.UUID | None = None,
        actor: User | None = None,
        emit_events: bool = True,
    ) -> None:
        """Reconcile stage, status, timestamps, close reason, and events.

        The stage's lifecycle drives the outcome when a stage is involved;
        a bare status change aligns the stage to the status's bucket. Emits
        LEAD_WON / LEAD_LOST only on an actual bucket change. Does not commit.
        """
        await self._ensure_defaults(organization_id)
        previous = lead.status
        if status is not None:
            lead.status = status

        stage = await self._pick_stage(
            organization_id, lead, stage_id=stage_id, status_changed=status is not None
        )
        if stage is not None:
            lead.stage_id = stage.id
            if stage.lifecycle is StageLifecycle.WON:
                lead.status = LeadStatus.WON
            elif stage.lifecycle is StageLifecycle.LOST:
                lead.status = LeadStatus.LOST
            else:
                lead.status = open_status_for(stage, previous)

        # Timestamps + close-reason bookkeeping keyed on the final status.
        if lead.status is LeadStatus.WON:
            if previous is not LeadStatus.WON:
                lead.won_at = utcnow()
            lead.lost_at = None
        elif lead.status is LeadStatus.LOST:
            if previous is not LeadStatus.LOST:
                lead.lost_at = utcnow()
            lead.won_at = None
        else:
            lead.won_at = None
            lead.lost_at = None
            lead.close_reason_id = None

        if close_reason_id is not None:
            reason = await self._reasons.get(organization_id, close_reason_id)
            if reason is None:
                raise AppError(
                    code="pipeline.close_reason_not_found",
                    message="Close reason not found",
                    status_code=404,
                )
            if bucket_of(lead.status) is not reason.lifecycle:
                raise AppError(
                    code="pipeline.close_reason_lifecycle_mismatch",
                    message="Close reason lifecycle does not match the stage",
                    status_code=400,
                )
            lead.close_reason_id = reason.id

        if not emit_events:
            return
        user_id = actor.id if actor is not None else None
        if lead.status is LeadStatus.WON and previous is not LeadStatus.WON:
            self._activity.add(
                ActivityLog(
                    organization_id=organization_id,
                    user_id=user_id,
                    lead_id=lead.id,
                    event_type=ActivityEventType.LEAD_WON,
                    entity_type="lead",
                    entity_id=lead.id,
                    description="Lead marked won",
                    metadata_={"stage_id": str(stage.id) if stage else None},
                    occurred_at=utcnow(),
                )
            )
        elif lead.status is LeadStatus.LOST and previous is not LeadStatus.LOST:
            self._activity.add(
                ActivityLog(
                    organization_id=organization_id,
                    user_id=user_id,
                    lead_id=lead.id,
                    event_type=ActivityEventType.LEAD_LOST,
                    entity_type="lead",
                    entity_id=lead.id,
                    description="Lead marked lost",
                    metadata_={"stage_id": str(stage.id) if stage else None},
                    occurred_at=utcnow(),
                )
            )

    # -- helpers --------------------------------------------------------

    async def _ensure_defaults(self, organization_id: uuid.UUID) -> None:
        stages = await self._stages.list(organization_id)
        next_position = max((s.position for s in stages), default=-1) + 1
        for name, lifecycle, is_default in _DEFAULT_STAGES:
            if any(s.name == name and s.lifecycle is lifecycle for s in stages):
                continue
            self._stages.add(
                PipelineStage(
                    organization_id=organization_id,
                    name=name,
                    lifecycle=lifecycle,
                    position=next_position,
                    is_default=is_default,
                )
            )
            next_position += 1

        reasons = await self._reasons.list(organization_id)
        for name, lifecycle, is_default in _DEFAULT_CLOSE_REASONS:
            if any(r.name == name and r.lifecycle is lifecycle for r in reasons):
                continue
            self._reasons.add(
                CloseReason(
                    organization_id=organization_id,
                    lifecycle=lifecycle,
                    name=name,
                    is_default=is_default,
                )
            )

    async def _pick_stage(
        self,
        organization_id: uuid.UUID,
        lead: Lead,
        *,
        stage_id: uuid.UUID | None,
        status_changed: bool,
    ) -> PipelineStage | None:
        if stage_id is not None:
            return await self._stages.get_or_404(organization_id, stage_id)
        current = (
            await self._stages.get(organization_id, lead.stage_id)
            if lead.stage_id is not None
            else None
        )
        if status_changed:
            bucket = bucket_of(lead.status)
            if current is None or current.lifecycle is not bucket:
                hint = lead.status.value if bucket is StageLifecycle.OPEN else None
                return await self._stages.get_default(organization_id, bucket, name_hint=hint)
            return current
        if current is not None:
            return current
        return await self._stages.get_default(organization_id, bucket_of(lead.status))
