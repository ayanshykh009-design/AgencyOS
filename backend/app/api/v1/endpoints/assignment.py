"""Assignment endpoints: rule management, manual assign, history, sweep."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query

from app.api.deps import CurrentUser, DbSession
from app.core.permissions import Permission, require_permission
from app.schemas.assignment import (
    AssignmentLogRead,
    AssignmentRuleRead,
    AssignmentRuleWrite,
    LeadAssignRequest,
)
from app.schemas.common import Page
from app.schemas.lead import LeadRead
from app.services.assignment_service import AssignmentService
from app.services.lead_service import LeadService

router = APIRouter()


@router.get(
    "/rules",
    response_model=AssignmentRuleRead | None,
    summary="Get the organization's assignment rule",
)
async def get_rule(db: DbSession, current_user: CurrentUser) -> AssignmentRuleRead | None:
    service = AssignmentService(db)
    rule = await service.get_rule(current_user.organization_id)
    return AssignmentRuleRead.model_validate(rule) if rule else None


@router.put(
    "/rules",
    response_model=AssignmentRuleRead,
    summary="Create or update the assignment rule",
    dependencies=[Depends(require_permission(Permission.LEAD_ASSIGN))],
)
async def put_rule(
    body: AssignmentRuleWrite,
    db: DbSession,
    current_user: CurrentUser,
) -> AssignmentRuleRead:
    service = AssignmentService(db)
    rule = await service.upsert_rule(
        current_user.organization_id,
        current_user,
        name=body.name,
        strategy=body.strategy,
        enabled=body.enabled,
        target_user_ids=body.target_user_ids,
    )
    return AssignmentRuleRead.model_validate(rule)


@router.post(
    "/assign-unassigned",
    response_model=dict[str, int],
    summary="Assign every unassigned lead per the active rule",
    dependencies=[Depends(require_permission(Permission.LEAD_ASSIGN))],
)
async def assign_unassigned(db: DbSession, current_user: CurrentUser) -> dict[str, int]:
    service = AssignmentService(db)
    count = await service.assign_unassigned(current_user.organization_id)
    return {"assigned": count}


@router.post(
    "/leads/{lead_id}/assign",
    response_model=LeadRead,
    summary="Manually assign (or unassign) a lead",
    dependencies=[Depends(require_permission(Permission.LEAD_ASSIGN))],
)
async def assign_lead(
    lead_id: uuid.UUID,
    body: LeadAssignRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> LeadRead:
    lead_service = LeadService(db)
    assignment = AssignmentService(db)
    lead = await lead_service.get(current_user.organization_id, lead_id)
    lead = await assignment.assign(
        current_user.organization_id,
        current_user,
        lead,
        to_user_id=body.user_id,
        reason=body.reason,
    )
    return LeadRead.model_validate(lead)


@router.get(
    "/leads/{lead_id}/history",
    response_model=Page[AssignmentLogRead],
    summary="Assignment history for a lead",
)
async def assignment_history(
    lead_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> Page[AssignmentLogRead]:
    service = AssignmentService(db)
    entries = await service.history(
        current_user.organization_id,
        lead_id=lead_id,
        limit=limit,
        offset=offset,
    )
    return Page(
        items=[AssignmentLogRead.model_validate(e) for e in entries],
        total=len(entries),
    )
