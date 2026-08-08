"""Communications endpoints: founder communications summary view."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, DbSession
from app.core.permissions import Permission, require_permission
from app.schemas.briefing import BriefingRead
from app.schemas.communication import CommunicationsSummary
from app.services.communication_service import CommunicationService

router = APIRouter()

_read = Depends(require_permission(Permission.NOTIFICATION_READ))
_growth_read = Depends(require_permission(Permission.GROWTH_READ))
_approval_read = Depends(require_permission(Permission.APPROVAL_READ))


@router.get(
    "/summary",
    response_model=CommunicationsSummary,
    summary="Founder communications digest (unread, pending, insights, latest briefing)",
    dependencies=[_read, _growth_read, _approval_read],
)
async def communications_summary(
    db: DbSession, current_user: CurrentUser
) -> CommunicationsSummary:
    service = CommunicationService(db)
    summary = await service.summary(current_user.organization_id, current_user.id)
    latest = (
        BriefingRead.model_validate(summary.latest_briefing)
        if summary.latest_briefing is not None
        else None
    )
    return CommunicationsSummary(
        unread_notifications=summary.unread_notifications,
        pending_approvals=summary.pending_approvals,
        active_insights=summary.active_insights,
        latest_briefing=latest,
    )
