"""User repository."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.enums import UserRole
from app.models.user import User


class UserRepository:
    """Data access for users (tenant-scoped)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: uuid.UUID) -> User | None:
        return await self._session.get(User, user_id)

    async def get_active_by_id_unscoped(self, user_id: uuid.UUID) -> User | None:
        """Load a user by id through the SECURITY DEFINER lookup.

        Used by the auth guard before any organization context exists: a plain
        ``session.get`` would be hidden by RLS (no ``app.current_organization_id``
        GUC set yet). The definer function bypasses RLS by design.
        """
        stmt = select(User).from_statement(
            text("SELECT * FROM public.app_get_user_by_id(:user_id)").bindparams(
                user_id=user_id
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        """Return a user by email (global lookup; email is unique app-wide).

        Routes through the SECURITY DEFINER lookup: email uniqueness is
        global-by-design, so the check must see across organizations even when
        no tenant context is active (register conflict resolution).
        """
        stmt = select(User).from_statement(
            text("SELECT * FROM public.app_get_user_by_email(:email)").bindparams(
                email=email.lower()
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_by_email(self, email: str) -> User | None:
        """Return an active user by email (global lookup).

        SECURITY DEFINER-backed so login works before any tenant context is
        established (RLS would otherwise hide every row with no GUC set).
        """
        stmt = select(User).from_statement(
            text(
                "SELECT * FROM public.app_find_active_user_by_email(:email)"
            ).bindparams(email=email.lower())
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_by_org(
        self, organization_id: uuid.UUID, *, limit: int = 100, offset: int = 0
    ) -> list[User]:
        stmt = (
            select(User)
            .where(User.organization_id == organization_id)
            .order_by(User.created_at)
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_org(self, organization_id: uuid.UUID) -> int:
        stmt = select(func.count(User.id)).where(User.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def count_active_by_org(self, organization_id: uuid.UUID) -> int:
        stmt = select(func.count(User.id)).where(
            User.organization_id == organization_id, User.is_active.is_(True)
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def count_role(self, organization_id: uuid.UUID, role: UserRole) -> int:
        stmt = select(func.count(User.id)).where(
            User.organization_id == organization_id, User.role == role
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def count_active_role(self, organization_id: uuid.UUID, role: UserRole) -> int:
        stmt = select(func.count(User.id)).where(
            User.organization_id == organization_id,
            User.role == role,
            User.is_active.is_(True),
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    _SALES_ROLES = (
        UserRole.MEMBER,
        UserRole.SALES_AGENT,
        UserRole.MANAGER,
        UserRole.ADMIN,
    )

    async def list_assignable(
        self,
        organization_id: uuid.UUID,
        *,
        user_ids: list[uuid.UUID] | None = None,
    ) -> list[User]:
        """Return active users who can own leads (optionally restricted)."""
        stmt = select(User).where(
            User.organization_id == organization_id,
            User.is_active.is_(True),
            User.role.in_(self._SALES_ROLES),
        )
        if user_ids:
            stmt = stmt.where(User.id.in_(user_ids))
        stmt = stmt.order_by(User.id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    def add(self, user: User) -> None:
        self._session.add(user)

    async def touch_last_login(self, user_id: uuid.UUID, now) -> None:
        user = await self.get(user_id)
        if user is not None:
            user.last_login_at = now

    async def get_or_404(self, organization_id: uuid.UUID, user_id: uuid.UUID) -> User:
        user = await self.get(user_id)
        if user is None or user.organization_id != organization_id:
            raise AppError(
                code="user.not_found",
                message="User not found",
                status_code=404,
            )
        return user

    @staticmethod
    async def handle_integrity_error(exc: IntegrityError) -> None:
        """Map duplicate-email errors to a friendly 409."""
        raise AppError(
            code="user.email_taken",
            message="A user with that email already exists",
            status_code=409,
        ) from exc
