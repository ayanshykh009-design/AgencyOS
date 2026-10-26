"""AuthToken repository (email verification / password reset)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import cast

from sqlalchemy import CursorResult, delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth_token import AuthToken


class AuthTokenRepository:
    """Data access for single-use account-lifecycle tokens."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, token: AuthToken) -> None:
        self._session.add(token)

    async def get_by_hash_any(self, token_hash: str) -> AuthToken | None:
        """Fetch a token by digest regardless of state.

        Routes through the SECURITY DEFINER lookup: verification/reset run
        before any tenant context exists, so a scoped SELECT would be hidden.
        """
        stmt = select(AuthToken).from_statement(
            text(
                "SELECT * FROM public.app_get_auth_token(:token_hash)"
            ).bindparams(token_hash=token_hash)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def invalidate_outstanding(
        self, user_id: uuid.UUID, purpose: str, *, now: datetime
    ) -> int:
        """Mark a user's still-unused tokens of ``purpose`` as used.

        Issuing a new token invalidates any earlier one so a stale link cannot
        be replayed after a fresh request.
        """
        stmt = (
            update(AuthToken)
            .where(
                AuthToken.user_id == user_id,
                AuthToken.purpose == purpose,
                AuthToken.used_at.is_(None),
            )
            .values(used_at=now)
        )
        result = await self._session.execute(stmt)
        return cast(CursorResult, result).rowcount or 0

    async def claim(self, token_id: uuid.UUID, purpose: str, *, now: datetime) -> bool:
        """Atomically claim a token for consumption.

        Returns True only if this request transitioned the token from unused
        to used (rowcount == 1). Checks purpose, unused state, and expiry
        in the same UPDATE so concurrent requests cannot both succeed.
        """
        stmt = (
            update(AuthToken)
            .where(
                AuthToken.id == token_id,
                AuthToken.purpose == purpose,
                AuthToken.used_at.is_(None),
                AuthToken.expires_at > now,
            )
            .values(used_at=now)
        )
        result = await self._session.execute(stmt)
        return (cast(CursorResult, result).rowcount or 0) == 1

    async def mark_used(self, token_id: uuid.UUID, *, now: datetime) -> None:
        stmt = (
            update(AuthToken)
            .where(AuthToken.id == token_id, AuthToken.used_at.is_(None))
            .values(used_at=now)
        )
        await self._session.execute(stmt)

    async def prune_expired(self, *, now: datetime) -> int:
        """Hard-delete expired tokens; returns the count."""
        stmt = delete(AuthToken).where(AuthToken.expires_at < now)
        result = await self._session.execute(stmt)
        return cast(CursorResult, result).rowcount or 0
