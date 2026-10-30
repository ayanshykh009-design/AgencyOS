"""UserRecoveryCode repository (MFA recovery codes)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import cast

from sqlalchemy import CursorResult, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_recovery_code import UserRecoveryCode


class UserRecoveryCodeRepository:
    """Data access for MFA recovery codes (tenant-scoped via the owning user)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, code: UserRecoveryCode) -> None:
        self._session.add(code)

    async def list_unused(self, user_id: uuid.UUID) -> list[UserRecoveryCode]:
        stmt = (
            select(UserRecoveryCode)
            .where(
                UserRecoveryCode.user_id == user_id,
                UserRecoveryCode.used_at.is_(None),
            )
            .order_by(UserRecoveryCode.created_at)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def mark_used(self, code_id: uuid.UUID, *, now: datetime) -> bool:
        """Atomically claim a recovery code. Returns True only if this request
        transitioned it from unused to used (rowcount == 1)."""
        stmt = (
            update(UserRecoveryCode)
            .where(UserRecoveryCode.id == code_id, UserRecoveryCode.used_at.is_(None))
            .values(used_at=now)
        )
        result = await self._session.execute(stmt)
        return (cast(CursorResult, result).rowcount or 0) == 1

    async def delete_all_for_user(self, user_id: uuid.UUID) -> int:
        stmt = delete(UserRecoveryCode).where(UserRecoveryCode.user_id == user_id)
        result = await self._session.execute(stmt)
        return cast(CursorResult, result).rowcount or 0
