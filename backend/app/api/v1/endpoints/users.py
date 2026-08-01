"""User endpoints (org-scoped user management)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, DbSession, require_role
from app.models.enums import UserRole
from app.schemas.common import Page
from app.schemas.user import UserCreate, UserRead, UserUpdate
from app.services.user_service import UserService

router = APIRouter()

# Only owners/admins may mutate users; any authenticated user may list.
_admin_only = require_role(UserRole.OWNER, UserRole.ADMIN)


@router.get(
    "",
    response_model=Page[UserRead],
    summary="List organization users",
)
async def list_users(
    db: DbSession,
    current_user: CurrentUser,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> Page[UserRead]:
    service = UserService(db)
    users = await service.list(
        current_user.organization_id, limit=limit, offset=offset
    )
    return Page(
        items=[UserRead.model_validate(u) for u in users], total=len(users)
    )


@router.get(
    "/{user_id}",
    response_model=UserRead,
    summary="Get a user",
)
async def get_user(
    user_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> UserRead:
    service = UserService(db)
    user = await service.get(current_user.organization_id, user_id)
    return UserRead.model_validate(user)


@router.post(
    "",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a user",
    dependencies=[Depends(_admin_only)],
)
async def create_user(
    body: UserCreate, db: DbSession, current_user: CurrentUser
) -> UserRead:
    service = UserService(db)
    data = body.model_dump()
    user = await service.create(current_user.organization_id, data)
    return UserRead.model_validate(user)


@router.patch(
    "/{user_id}",
    response_model=UserRead,
    summary="Update a user",
    dependencies=[Depends(_admin_only)],
)
async def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> UserRead:
    service = UserService(db)
    user = await service.update(
        current_user.organization_id,
        user_id,
        body.model_dump(exclude_unset=True),
    )
    return UserRead.model_validate(user)
