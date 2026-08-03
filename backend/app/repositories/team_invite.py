"""TeamInvite repository."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import InviteStatus
from app.models.team_invite import TeamInvite


class TeamInviteRepository:
    """Data access for team invites (tenant-scoped)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, invite: TeamInvite) -> None:
        self._session.add(invite)

    async def get(self, invite_id: uuid.UUID) -> TeamInvite | None:
        return await self._session.get(TeamInvite, invite_id)

    async def get_by_org(
        self, organization_id: uuid.UUID, invite_id: uuid.UUID
    ) -> TeamInvite | None:
        stmt = select(TeamInvite).where(
            TeamInvite.organization_id == organization_id,
            TeamInvite.id == invite_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_token_hash(self, token_hash: str) -> TeamInvite | None:
        stmt = select(TeamInvite).where(TeamInvite.token_hash == token_hash)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_pending_by_email(
        self, organization_id: uuid.UUID, email: str
    ) -> TeamInvite | None:
        stmt = select(TeamInvite).where(
            TeamInvite.organization_id == organization_id,
            TeamInvite.email == email,
            TeamInvite.status == InviteStatus.PENDING,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list(
        self,
        organization_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[TeamInvite]:
        stmt = (
            select(TeamInvite)
            .where(TeamInvite.organization_id == organization_id)
            .order_by(TeamInvite.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def expire_stale(
        self, organization_id: uuid.UUID, now: datetime
    ) -> None:
        """Mark overdue pending invites as expired (best-effort sweep)."""
        stmt = select(TeamInvite).where(
            TeamInvite.organization_id == organization_id,
            TeamInvite.status == InviteStatus.PENDING,
            TeamInvite.expires_at <= now,
        )
        result = await self._session.execute(stmt)
        for invite in result.scalars().all():
            invite.status = InviteStatus.EXPIRED
