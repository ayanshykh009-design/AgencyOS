"""Export endpoints: download org-scoped lead data as CSV or JSON."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response

from app.api.deps import CurrentUser, DbSession
from app.core.permissions import Permission, require_permission
from app.models.enums import LeadStatus
from app.services.export_service import ExportService

router = APIRouter()

_read = Depends(require_permission(Permission.EXPORT))


@router.get(
    "/leads",
    summary="Export leads as CSV or JSON",
    dependencies=[_read],
)
async def export_leads(
    db: DbSession,
    current_user: CurrentUser,
    fmt: str = Query(default="csv", pattern="^(csv|json)$"),
    query: str | None = None,
    status: LeadStatus | None = None,
    source_id: uuid.UUID | None = None,
    owner_user_id: uuid.UUID | None = None,
    min_score: int | None = Query(default=None, ge=0, le=100),
    max_score: int | None = Query(default=None, ge=0, le=100),
) -> Response:
    """Return matching leads as an attachment in the requested format."""
    service = ExportService(db)
    payload = await service.export_leads(
        current_user.organization_id,
        fmt=fmt,
        query=query,
        status=status,
        source_id=source_id,
        owner_user_id=owner_user_id,
        min_score=min_score,
        max_score=max_score,
    )
    media_type = "text/csv" if fmt == "csv" else "application/json"
    return Response(
        content=payload,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="leads.{fmt}"'},
    )
