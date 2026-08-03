"""User service: org-scoped user management.

Guards: an actor may only manage strictly less-privileged peers, and the
last active owner can never be demoted or deactivated (prevents lockout).
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.permissions import role_can_manage
from app.core.security import hash_password
from app.models.activity_log import ActivityLog
from app.models.enums import ActivityEventType, UserRole
from app.models.user import User
from app.repositories.activity_log import ActivityLogRepository
from app.repositories.user import UserRepository
from app.services.base import commit_with_retry, utcnow


class UserService:
    """Owns user business rules and the transaction boundary."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._logs = ActivityLogRepository(session)

    async def list(
        self, organization_id: uuid.UUID, *, limit: int = 100, offset: int = 0
    ) -> list[User]:
        return await self._users.list_by_org(
            organization_id, limit=limit, offset=offset
        )

    async def get(self, organization_id: uuid.UUID, user_id: uuid.UUID) -> User:
        return await self._users.get_or_404(organization_id, user_id)

    async def create(
        self,
        organization_id: uuid.UUID,
        actor: User,
        data: dict[str, Any],
    ) -> User:
        email = str(data["email"]).strip().lower()
        if await self._users.get_by_email(email) is not None:
            raise AppError(
                code="user.email_taken",
                message="A user with that email already exists",
                status_code=409,
            )
        role = UserRole(data.get("role", UserRole.MEMBER))
        if not role_can_manage(actor.role, role):
            raise AppError(
                code="user.role_denied",
                message="You cannot create a member with that role",
                status_code=403,
            )
        password = data.get("password")
        user = User(
            organization_id=organization_id,
            email=email,
            full_name=data["full_name"],
            role=role,
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
        actor: User,
        user_id: uuid.UUID,
        data: dict[str, Any],
    ) -> User:
        user = await self._users.get_or_404(organization_id, user_id)
        self._validate_actor(actor, user, data)

        role_changed = "role" in data and UserRole(data["role"]) != user.role
        if role_changed:
            new_role = UserRole(data["role"])
            await self._ensure_owner_safety(
                organization_id, user, new_role=new_role
            )
            self._logs.add(
                ActivityLog(
                    organization_id=organization_id,
                    user_id=actor.id,
                    event_type=ActivityEventType.USER_ROLE_CHANGED,
                    entity_type="user",
                    entity_id=user.id,
                    description=(
                        f"Changed role of {user.email} "
                        f"from {user.role.value} to {new_role.value}"
                    ),
                    metadata_={"from": user.role.value, "to": new_role.value},
                    occurred_at=utcnow(),
                )
            )
            user.role = new_role

        if "full_name" in data:
            user.full_name = data["full_name"]
        if "is_active" in data:
            is_active = bool(data["is_active"])
            if is_active != user.is_active:
                await self._ensure_owner_safety(
                    organization_id, user, activating=is_active
                )
                self._logs.add(
                    ActivityLog(
                        organization_id=organization_id,
                        user_id=actor.id,
                        event_type=ActivityEventType.USER_STATUS_CHANGED,
                        entity_type="user",
                        entity_id=user.id,
                        description=(
                            f"{'Reactivated' if is_active else 'Deactivated'} "
                            f"{user.email}"
                        ),
                        metadata_={"active": is_active},
                        occurred_at=utcnow(),
                    )
                )
                user.is_active = is_active
        if "password" in data and data["password"]:
            user.password_hash = hash_password(data["password"])
        await commit_with_retry(self._session)
        return user

    def _validate_actor(self, actor: User, target: User, data: dict[str, Any]) -> None:
        """Reject self role/status changes and managing peers of equal privilege."""
        is_self = actor.id == target.id
        if "role" in data:
            new_role = UserRole(data["role"])
            if is_self:
                raise AppError(
                    code="user.self_role_change",
                    message="You cannot change your own role",
                    status_code=400,
                )
            if not role_can_manage(actor.role, new_role):
                raise AppError(
                    code="user.role_denied",
                    message="You cannot assign a role at or above your own",
                    status_code=403,
                )
            if not role_can_manage(actor.role, target.role):
                raise AppError(
                    code="user.manage_denied",
                    message="You cannot manage members with an equal or higher role",
                    status_code=403,
                )
        if "is_active" in data:
            if is_self:
                raise AppError(
                    code="user.self_status_change",
                    message="You cannot change your own account status",
                    status_code=400,
                )
            if not role_can_manage(actor.role, target.role):
                raise AppError(
                    code="user.manage_denied",
                    message="You cannot manage members with an equal or higher role",
                    status_code=403,
                )

    async def _ensure_owner_safety(
        self,
        organization_id: uuid.UUID,
        owner: User,
        *,
        new_role: UserRole | None = None,
        activating: bool | None = None,
    ) -> None:
        """Block the last-active-owner demotion/deactivation (lockout guard)."""
        if owner.role is not UserRole.OWNER:
            return
        demoted = new_role is not None and new_role is not UserRole.OWNER
        deactivated = activating is False
        if not (demoted or deactivated):
            return
        active_owners = await self._users.count_active_role(
            organization_id, UserRole.OWNER
        )
        # This owner is active and about to cease being an active owner, so
        # at least one other active owner must remain.
        if active_owners < 2:
            raise AppError(
                code="user.last_owner",
                message="The last active owner cannot be demoted or deactivated",
                status_code=400,
            )
