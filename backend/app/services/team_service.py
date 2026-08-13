"""Team service: invites, role management, and membership rules.

Owns the invite transaction boundary. Invites are delivered as one-time
links (no email provider is wired): the raw token is returned exactly once
in the create response and only its SHA-256 digest is stored.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from hashlib import sha256
from secrets import token_urlsafe

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.core.permissions import role_can_invite
from app.core.security import hash_password
from app.models.activity_log import ActivityLog
from app.models.enums import ActivityEventType, InviteStatus, UserRole
from app.models.team_invite import TeamInvite
from app.models.user import User
from app.repositories.activity_log import ActivityLogRepository
from app.repositories.organization import OrganizationRepository
from app.repositories.team_invite import TeamInviteRepository
from app.repositories.user import UserRepository
from app.services.base import commit_with_retry, utcnow

_INVITE_TTL_DAYS = 7


def _token_hash(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


class TeamService:
    """Owns team membership rules and the transaction boundary."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._invites = TeamInviteRepository(session)
        self._users = UserRepository(session)
        self._orgs = OrganizationRepository(session)
        self._logs = ActivityLogRepository(session)

    # -- invites ---------------------------------------------------------

    async def create_invite(
        self,
        organization_id: uuid.UUID,
        actor: User,
        *,
        email: str,
        full_name: str | None,
        role: UserRole,
    ) -> tuple[TeamInvite, str]:
        """Create a pending invite and return (invite, raw_token)."""
        email = email.strip().lower()
        if not role_can_invite(actor.role, role):
            raise AppError(
                code="team.invite_role_denied",
                message="You cannot invite a member with that role",
                status_code=403,
            )
        if await self._users.get_by_email(email) is not None:
            raise AppError(
                code="team.user_exists",
                message="A user with that email already exists",
                status_code=409,
            )
        existing = await self._invites.get_pending_by_email(organization_id, email)
        if existing is not None:
            raise AppError(
                code="team.invite_exists",
                message="A pending invite for that email already exists",
                status_code=409,
            )

        raw_token = token_urlsafe(48)
        invite = TeamInvite(
            organization_id=organization_id,
            email=email,
            full_name=full_name,
            role=role,
            token_hash=_token_hash(raw_token),
            invited_by_user_id=actor.id,
            status=InviteStatus.PENDING,
            expires_at=utcnow() + timedelta(days=_INVITE_TTL_DAYS),
        )
        self._invites.add(invite)
        self._logs.add(
            ActivityLog(
                organization_id=organization_id,
                user_id=actor.id,
                event_type=ActivityEventType.USER_INVITED,
                entity_type="team_invite",
                entity_id=invite.id,
                description=f"Invited {email} as {role.value}",
                metadata_={"email": email, "role": role.value},
                occurred_at=utcnow(),
            )
        )
        try:
            await commit_with_retry(self._session)
        except IntegrityError as exc:
            await self._session.rollback()
            raise AppError(
                code="team.invite_failed",
                message="Could not create the invite",
                status_code=409,
            ) from exc
        return invite, raw_token

    async def list_invites(
        self,
        organization_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[TeamInvite]:
        now = utcnow()
        await self._invites.expire_stale(organization_id, now)
        await commit_with_retry(self._session)
        return await self._invites.list(organization_id, limit=limit, offset=offset)

    async def revoke_invite(
        self,
        organization_id: uuid.UUID,
        actor: User,
        invite_id: uuid.UUID,
    ) -> TeamInvite:
        invite = await self._invites.get_by_org(organization_id, invite_id)
        if invite is None:
            raise AppError(
                code="team.invite_not_found",
                message="Invite not found",
                status_code=404,
            )
        if invite.status is not InviteStatus.PENDING:
            raise AppError(
                code="team.invite_not_pending",
                message="Only pending invites can be revoked",
                status_code=400,
            )
        invite.status = InviteStatus.REVOKED
        invite.revoked_at = utcnow()
        self._logs.add(
            ActivityLog(
                organization_id=organization_id,
                user_id=actor.id,
                event_type=ActivityEventType.INVITE_REVOKED,
                entity_type="team_invite",
                entity_id=invite.id,
                description=f"Revoked invite for {invite.email}",
                occurred_at=utcnow(),
            )
        )
        await commit_with_retry(self._session)
        return invite

    async def lookup_invite(self, token: str) -> TeamInvite:
        """Return the invite for a token (rejecting non-pending/expired)."""
        invite = await self._invites.get_by_token_hash(_token_hash(token))
        if invite is None:
            raise AppError(
                code="team.invite_invalid",
                message="Invite not found",
                status_code=404,
            )
        if invite.status is not InviteStatus.PENDING:
            raise AppError(
                code="team.invite_invalid",
                message="This invite has already been used or revoked",
                status_code=404,
            )
        if invite.expires_at <= utcnow():
            invite.status = InviteStatus.EXPIRED
            await commit_with_retry(self._session)
            raise AppError(
                code="team.invite_expired",
                message="This invite has expired",
                status_code=404,
            )
        return invite

    async def accept_invite(self, token: str, full_name: str, password: str) -> TeamInvite:
        """Accept an invite, create the account, and return the consumed invite."""
        invite = await self.lookup_invite(token)

        if await self._users.get_by_email(invite.email) is not None:
            invite.status = InviteStatus.REVOKED
            await commit_with_retry(self._session)
            raise AppError(
                code="team.user_exists",
                message="A user with that email already exists",
                status_code=409,
            )

        user = User(
            organization_id=invite.organization_id,
            email=invite.email,
            full_name=full_name,
            role=invite.role,
            password_hash=hash_password(password),
        )
        self._users.add(user)
        try:
            await self._session.flush()
        except IntegrityError:
            await self._session.rollback()
            raise AppError(
                code="team.user_exists",
                message="A user with that email already exists",
                status_code=409,
            ) from None

        invite.status = InviteStatus.ACCEPTED
        invite.accepted_at = utcnow()
        invite.accepted_user_id = user.id
        self._logs.add(
            ActivityLog(
                organization_id=invite.organization_id,
                user_id=user.id,
                event_type=ActivityEventType.INVITE_ACCEPTED,
                entity_type="team_invite",
                entity_id=invite.id,
                description=f"{invite.email} joined as {invite.role.value}",
                occurred_at=utcnow(),
            )
        )
        await commit_with_retry(self._session)
        return invite

    @staticmethod
    def invite_url(raw_token: str) -> str:
        """Return the one-time acceptance URL for an invite token."""
        return f"{settings.FRONTEND_URL}/invite/{raw_token}"

    async def organization_name(self, organization_id: uuid.UUID) -> str | None:
        org = await self._orgs.get(organization_id)
        return org.name if org is not None else None
