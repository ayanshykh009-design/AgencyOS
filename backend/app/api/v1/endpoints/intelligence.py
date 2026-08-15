"""Intelligence endpoints — Founder Intelligence & Growth Triage (M9).

Read surface: list/get/summarize signals (founder_read).
Write surface: acknowledge/dismiss a signal (founder_manage) and an optional
manual sweep trigger (founder_manage). Signals are written by the triage
worker; the API never mutates the M7/M8 source rows a signal points at.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.core.errors import AppError
from app.core.permissions import Permission, require_permission
from app.models.enums import (
    IntelligenceSignalStatus,
    SignalCategory,
    SignalSourceType,
)
from app.schemas.intelligence_signal import (
    IntelligenceSignalListResponse,
    IntelligenceSignalRead,
    IntelligenceSignalSummary,
    IntelligenceSignalUpdate,
)
from app.services.intelligence import (
    FounderIntelligenceService,
    IntelligenceTriageService,
)

router = APIRouter()

_read = Depends(require_permission(Permission.FOUNDER_READ))
_manage = Depends(require_permission(Permission.FOUNDER_MANAGE))


def _ensure_triage_enabled() -> None:
    if not settings.INTELLIGENCE_TRIAGE_ENABLED:
        raise AppError(
            code="intelligence_triage.runtime_disabled",
            message="Intelligence triage is not enabled",
            status_code=503,
        )


@router.get(
    "/signals",
    response_model=IntelligenceSignalListResponse,
    summary="List triaged intelligence signals (priority-first, optional filters)",
    dependencies=[_read],
)
async def list_signals(
    db: DbSession,
    current_user: CurrentUser,
    status_filter: IntelligenceSignalStatus | None = Query(
        default=None, alias="status"
    ),
    category: SignalCategory | None = None,
    source_type: SignalSourceType | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> IntelligenceSignalListResponse:
    service = FounderIntelligenceService(db)
    items = await service.list_signals(
        current_user.organization_id,
        status=status_filter,
        category=category,
        source_type=source_type,
        limit=limit,
        offset=offset,
    )
    return IntelligenceSignalListResponse(
        items=[IntelligenceSignalRead.model_validate(s) for s in items], total=len(items)
    )


@router.get(
    "/signals/{signal_id}",
    response_model=IntelligenceSignalRead,
    summary="Get one intelligence signal",
    dependencies=[_read],
)
async def get_signal(
    signal_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> IntelligenceSignalRead:
    service = FounderIntelligenceService(db)
    signal = await service.get_signal(current_user.organization_id, signal_id)
    return IntelligenceSignalRead.model_validate(signal)


@router.patch(
    "/signals/{signal_id}",
    response_model=IntelligenceSignalRead,
    summary="Acknowledge or dismiss an intelligence signal",
    dependencies=[_manage],
)
async def update_signal(
    signal_id: uuid.UUID,
    body: IntelligenceSignalUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> IntelligenceSignalRead:
    service = FounderIntelligenceService(db)
    signal = await service.update_status(
        current_user.organization_id,
        signal_id,
        body.status,
        actor_user_id=current_user.id,
    )
    return IntelligenceSignalRead.model_validate(signal)


@router.get(
    "/summary",
    response_model=IntelligenceSignalSummary,
    summary="Roll-up counts over this org's intelligence signals",
    dependencies=[_read],
)
async def signal_summary(db: DbSession, current_user: CurrentUser) -> IntelligenceSignalSummary:
    service = FounderIntelligenceService(db)
    data = await service.summarize(current_user.organization_id)
    return IntelligenceSignalSummary(**data)


@router.post(
    "/triage/run",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    summary="Run a manual triage sweep for the caller's org",
    dependencies=[_manage],
)
async def run_triage(db: DbSession, current_user: CurrentUser) -> dict:
    """Deterministic sweep for the caller's org; commits within this request.

    Refuses to run when ``INTELLIGENCE_TRIAGE_ENABLED`` is off (fail closed).
    """
    _ensure_triage_enabled()
    service = IntelligenceTriageService(db)
    counters = await service.run_sweep_for_org(current_user.organization_id)
    await db.commit()

    read = FounderIntelligenceService(db)
    signals = await read.list_signals(
        current_user.organization_id, status=IntelligenceSignalStatus.ACTIVE, limit=50
    )
    narrative = await read.generate_narrative(current_user.organization_id, signals)
    return {
        "candidates": counters["candidates"],
        "created": counters["created"],
        "updated": counters["updated"],
        "superseded": counters["superseded"],
        "high_priority": counters["high_priority"],
        "narrative": narrative,
    }
