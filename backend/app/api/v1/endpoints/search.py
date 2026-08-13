"""Search endpoint: unified text search across leads, tasks, and notes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import CurrentUser, DbSession
from app.core.permissions import Permission, require_permission
from app.schemas.search import SearchResponse
from app.services.search_service import SearchService

router = APIRouter()

_read = Depends(require_permission(Permission.LEAD_READ))


@router.get(
    "",
    response_model=SearchResponse,
    summary="Search across leads, tasks, and notes",
    dependencies=[_read],
)
async def global_search(
    db: DbSession,
    current_user: CurrentUser,
    q: str = Query(default="", min_length=1, max_length=255),
    limit: int = Query(default=10, ge=1, le=50),
) -> SearchResponse:
    """Run ``q`` against leads, tasks, and notes within the organization."""
    query = q.strip()
    if not query:
        return SearchResponse(query="")
    service = SearchService(db)
    data = await service.search(
        current_user.organization_id,
        query=query,
        limit=limit,
    )
    return SearchResponse.model_validate(data)
