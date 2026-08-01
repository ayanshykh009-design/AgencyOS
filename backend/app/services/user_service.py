"""User service: org-scoped user management."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.security import hash_password
from app.models.enums import UserRole
from app.models.user import User
from app.repositories.user import UserRepository
from app.services.base import commit_with_retry


class UserService:
    """Owns user business rules and the transaction boundary."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)

    async def list(
        self, organization_id: uuid.UUID, *, limit: int = 100, offset: int = 0
    ) -> list[User]:
        return await self._users.list_by_org(
            organization_id, limit=limit, offset=offset
        )

    async def get(self, organization_id: uuid.UUID, user_id: uuid.UUID) -> User:
        return await self._users.get_or_404(organization_id, user_id)

    async def create(
        self, organization_id: uuid.UUID, data: dict[str, Any]
    ) -> User:
        email = str(data["email"]).strip().lower()
        if await self._users.get_by_email(email) is not None:
            raise AppError(
                code="user.email_taken",
                message="A user with that email already exists",
                status_code=409,
            )
        password = data.get("password")
        user = User(
            organization_id=organization_id,
            email=email,
            full_name=data["full_name"],
            role=UserRole(data.get("role", UserRole.MEMBER)),
            is_active=bool(data.get("is_active", True)),
            password_hash=hash_password(password) if password else None,
        )
        self._users.add(user)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            await self._users.handle_integrity_error(exc)
        await commit_with_retry(self._session)
        return user

    async def update(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        data: dict[str, Any],
    ) -> User:
        user = await self._users.get_or_404(organization_id, user_id)
        if "full_name" in data:
            user.full_name = data["full_name"]
        if "role" in data:
            user.role = UserRole(data["role"])
        if "is_active" in data:
            user.is_active = bool(data["is_active"])
        if "password" in data and data["password"]:
            user.password_hash = hash_password(data["password"])
        await commit_with_retry(self._session)
        return user
