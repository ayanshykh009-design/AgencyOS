"""Shared FastAPI dependencies.

Dependencies are reusable injectables for route handlers:
- `get_db` (async SQLAlchemy session),
- `get_current_user` (JWT auth guard),
- `require_role` (role-based authorization),
- `get_supabase` (Supabase admin client).

Only dependency plumbing belongs here — never business rules.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import AppError
from app.core.security import require_valid_token
from app.models.enums import UserRole
from app.models.user import User
from app.repositories.user import UserRepository

# Re-export for convenient `Annotated` typing in routers.
DbSession = Annotated[AsyncSession, Depends(get_db)]

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    db: DbSession,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> User:
    """Validate the bearer JWT and load the active user."""
    if credentials is None:
        raise AppError(
            code="auth.missing_token",
            message="Not authenticated",
            status_code=401,
        )
    payload = require_valid_token(credentials.credentials)
    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError, TypeError):
        raise AppError(
            code="auth.invalid_token",
            message="Invalid or expired token",
            status_code=401,
        ) from None
    user = await UserRepository(db).get(user_id)
    if user is None or not user.is_active:
        raise AppError(
            code="auth.user_unavailable",
            message="Account not found or disabled",
            status_code=401,
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(*roles: UserRole):
    """Return a dependency that enforces one of the given roles."""

    async def _require_role(current_user: CurrentUser) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=403,
                detail="Insufficient permissions for this operation",
            )
        return current_user

    return _require_role
