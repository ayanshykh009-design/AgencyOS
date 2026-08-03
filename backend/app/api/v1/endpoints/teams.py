"""Team endpoints: invite members, list/revoke invites, accept invites.

Invite accept is intentionally unauthenticated (the invitee has no account
yet); it validates against the stored token digest and is rate-limited.
Everything else requires a session and the invite-management permission.

NOTE: intentionally does NOT use ``from __future__ import annotations``;
slowapi's ``@limiter.limit`` wrapper breaks FastAPI's forward-ref resolution.
"""
import uuid

from fastapi import APIRouter, Depends, Query, Request, status

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.core.permissions import Permission, require_permission
from app.core.rate_limit import limiter
from app.schemas.common import Page
from app.schemas.team import (
    TeamInviteAccept,
    TeamInviteCreate,
    TeamInviteCreateResponse,
    TeamInviteLookup,
    TeamInviteRead,
)
from app.services.team_service import TeamService

router = APIRouter()


@router.post(
    "",
    response_model=TeamInviteCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Invite a new team member",
    dependencies=[Depends(require_permission(Permission.INVITE_MANAGE))],
)
async def invite_member(
    body: TeamInviteCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> TeamInviteCreateResponse:
    """Create a one-time invite link for a new team member."""
    service = TeamService(db)
    invite, raw_token = await service.create_invite(
        current_user.organization_id,
        current_user,
        email=body.email,
        full_name=body.full_name,
        role=body.role,
    )
    response = TeamInviteCreateResponse.model_validate(invite)
    response.invite_url = service.invite_url(raw_token)
    return response


@router.get(
    "",
    response_model=Page[TeamInviteRead],
    summary="List team invites",
    dependencies=[Depends(require_permission(Permission.INVITE_MANAGE))],
)
async def list_invites(
    db: DbSession,
    current_user: CurrentUser,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> Page[TeamInviteRead]:
    service = TeamService(db)
    invites = await service.list_invites(
        current_user.organization_id, limit=limit, offset=offset
    )
    return Page(
        items=[TeamInviteRead.model_validate(i) for i in invites],
        total=len(invites),
    )


@router.post(
    "/{invite_id}/revoke",
    response_model=TeamInviteRead,
    summary="Revoke a pending invite",
    dependencies=[Depends(require_permission(Permission.INVITE_MANAGE))],
)
async def revoke_invite(
    invite_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> TeamInviteRead:
    service = TeamService(db)
    invite = await service.revoke_invite(
        current_user.organization_id, current_user, invite_id
    )
    return TeamInviteRead.model_validate(invite)


@router.get(
    "/public/{token}",
    response_model=TeamInviteLookup,
    summary="Resolve invite details for the acceptance screen",
)
async def lookup_invite(
    token: str, db: DbSession
) -> TeamInviteLookup:
    """Return non-sensitive invite details for a token (no session)."""
    service = TeamService(db)
    invite = await service.lookup_invite(token)
    data = TeamInviteLookup.model_validate(invite)
    data.organization_name = await service.organization_name(
        invite.organization_id
    )
    return data


@router.post(
    "/accept",
    response_model=TeamInviteRead,
    summary="Accept an invite and create the account",
)
@limiter.limit(settings.RATE_LIMIT_STRICT)
async def accept_invite(
    request: Request, body: TeamInviteAccept, db: DbSession
) -> TeamInviteRead:
    """Validate the token, create the user, and return the consumed invite."""
    service = TeamService(db)
    invite = await service.accept_invite(
        body.token, full_name=body.full_name, password=body.password
    )
    return TeamInviteRead.model_validate(invite)
