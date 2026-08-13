"""Refresh token repository (rotation-based auth)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import cast

from sqlalchemy import CursorResult, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.refresh_token import RefreshToken


class RefreshTokenRepository:
    """Data access for refresh tokens."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, token: RefreshToken) -> None:
        self._session.add(token)

    async def get_valid(self, token_hash: str, *, now: datetime) -> RefreshToken | None:
        """Fetch a non-revoked, non-expired token by its digest."""
        stmt = select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > now,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def revoke(self, token_id: uuid.UUID, *, now: datetime) -> None:
        stmt = (
            update(RefreshToken)
            .where(RefreshToken.id == token_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        await self._session.execute(stmt)

    async def mark_replaced(
        self, token_id: uuid.UUID, replaced_by: uuid.UUID, *, now: datetime
    ) -> None:
        """Rotate: revoke the old token and link it to its successor."""
        await self.revoke(token_id, now=now)
        stmt = (
            update(RefreshToken).where(RefreshToken.id == token_id).values(replaced_by=replaced_by)
        )
        await self._session.execute(stmt)

    async def revoke_all_for_user(self, user_id: uuid.UUID, *, now: datetime) -> int:
        """Revoke every outstanding token for a user; returns the count."""
        stmt = (
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > now,
            )
            .values(revoked_at=now)
        )
        result = await self._session.execute(stmt)
        return cast(CursorResult, result).rowcount or 0

    async def prune_expired(self, *, now: datetime) -> int:
        """Hard-delete expired/revoked tokens older than 7 days; returns count."""
        stmt = delete(RefreshToken).where(RefreshToken.expires_at < now)
        result = await self._session.execute(stmt)
        return cast(CursorResult, result).rowcount or 0
