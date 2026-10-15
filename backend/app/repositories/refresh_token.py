"""Refresh token repository (rotation-based auth)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import cast

from sqlalchemy import CursorResult, delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.refresh_token import RefreshToken


class RefreshTokenRepository:
    """Data access for refresh tokens."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, token: RefreshToken) -> None:
        self._session.add(token)

    async def get_valid(self, token_hash: str, *, now: datetime) -> RefreshToken | None:
        """Fetch a non-revoked, non-expired token by its digest.

        Routes through the SECURITY DEFINER lookup: refresh runs before any
        tenant context exists, so a plain scoped SELECT would be hidden by RLS.
        """
        stmt = select(RefreshToken).from_statement(
            text(
                "SELECT * FROM public.app_get_valid_refresh_token(:token_hash, :now)"
            ).bindparams(token_hash=token_hash, now=now)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_any(self, token_hash: str) -> RefreshToken | None:
        """Fetch a token by digest regardless of revoked/expired state.

        Used for reuse detection: an already-rotated token is revoked, so the
        valid-only lookup would hide it. Routes through the SECURITY DEFINER
        lookup because refresh runs before any tenant context exists.
        """
        stmt = select(RefreshToken).from_statement(
            text(
                "SELECT * FROM public.app_get_refresh_token_any(:token_hash)"
            ).bindparams(token_hash=token_hash)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def revoke_family(self, family_id: uuid.UUID, *, now: datetime) -> int:
        """Revoke every still-active token in a family; returns the count."""
        stmt = (
            update(RefreshToken)
            .where(
                RefreshToken.family_id == family_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        result = await self._session.execute(stmt)
        return cast(CursorResult, result).rowcount or 0

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
