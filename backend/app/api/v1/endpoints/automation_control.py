"""Automation control endpoints: global pause/resume kill switch.

Exports a thin HTTP layer around ``AutomationControlService`` that enforces
``AUTOMATION_CONTROL`` permissions (admin-only) and writes to the audit log via
the ``ActivityLog`` table. Follows the pattern established elsewhere (e.g.,
``workflow_executions.py``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, DbSession
from app.core.permissions import Permission, require_permission
from app.schemas.system_settings import (
    SystemSettingPauseRequest,
    SystemSettingResumeRequest,
    SystemSettingStatusResponse,
)
from app.services.automation_control_service import AutomationControlService

if TYPE_CHECKING:
    pass

router = APIRouter()

_admin = Depends(require_permission(Permission.AUTOMATION_CONTROL))


@router.get(
    "/status",
    response_model=SystemSettingStatusResponse,
    summary="Get automation status",
    dependencies=[_admin],
)
async def get_automation_status(
    db: DbSession,
    current_user: CurrentUser,
) -> SystemSettingStatusResponse:
    """Return the current automation enabled status and pause metadata.

    Admin-only endpoint that returns whether automation is running and any
    pause details (who paused it, when, and why).
    """
    service = AutomationControlService(db)
    status = await service.get_status()
    return SystemSettingStatusResponse(
        enabled=status.enabled,
        paused_by=status.paused_by,
        paused_at=status.paused_at,
        paused_reason=status.paused_reason,
    )


@router.post(
    "/pause",
    response_model=SystemSettingStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Pause automation",
    dependencies=[_admin],
)
async def pause_automation(
    request: SystemSettingPauseRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> SystemSettingStatusResponse:
    """Pause all automation (operator-only).

    Sets ``automation.enabled`` to false, stores pause metadata, and writes an
    ``activity_logs`` entry with ``AUTOMATION_PAUSED``. All execution phases,
    queue, and schedule dispatch will be blocked until this endpoint is called
    with ``/resume``.
    """
    service = AutomationControlService(db)
    status = await service.pause(
        user_id=current_user.id,
        reason=request.reason,
        organization_id=current_user.organization_id,
    )
    return SystemSettingStatusResponse(
        enabled=status.enabled,
        paused_by=status.paused_by,
        paused_at=status.paused_at,
        paused_reason=status.paused_reason,
    )


@router.post(
    "/resume",
    response_model=SystemSettingStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Resume automation",
    dependencies=[_admin],
)
async def resume_automation(
    request: SystemSettingResumeRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> SystemSettingStatusResponse:
    """Resume automation after a pause (operator-only).

    Clears the pause metadata and sets ``automation.enabled`` back to true.
    Writes an ``activity_logs`` entry with ``AUTOMATION_RESUMED``.
    """
    service = AutomationControlService(db)
    status = await service.resume(
        user_id=current_user.id,
        organization_id=current_user.organization_id,
    )
    return SystemSettingStatusResponse(
        enabled=status.enabled,
        paused_by=status.paused_by,
        paused_at=status.paused_at,
        paused_reason=status.paused_reason,
    )
