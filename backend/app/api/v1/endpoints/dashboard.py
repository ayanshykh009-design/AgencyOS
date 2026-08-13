"""Dashboard endpoints: aggregate snapshot for the UI."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.dashboard import DashboardSummary
from app.services.dashboard_service import DashboardService

router = APIRouter()


@router.get(
    "/summary",
    response_model=DashboardSummary,
    summary="Dashboard summary snapshot",
)
async def dashboard_summary(db: DbSession, current_user: CurrentUser) -> DashboardSummary:
    """Return aggregate metrics for the dashboard landing page."""
    service = DashboardService(db)
    data = await service.summary(current_user.organization_id)
    return DashboardSummary.model_validate(data)
