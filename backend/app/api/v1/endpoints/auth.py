"""Authentication endpoints: register, login, refresh, logout, me.

Layered flow: this router -> app/services/auth_service.py -> repositories.

NOTE: intentionally does NOT use ``from __future__ import annotations``.
slowapi's ``functools.wraps`` copies string annotations and FastAPI then
resolves them against slowapi's globals, producing unresolved ForwardRefs.
Real (non-string) annotations keep ``get_type_hints`` working.
"""
from fastapi import APIRouter, Request, status

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.core.rate_limit import limiter
from app.schemas.auth import (
    AuthResponse,
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
)
from app.schemas.user import UserRead
from app.services.auth_service import AuthService

router = APIRouter()


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register an organization and its owner",
)
@limiter.limit(settings.RATE_LIMIT_STRICT)
async def register(request: Request, body: RegisterRequest, db: DbSession) -> AuthResponse:
    """Create a new organization + owner account and return a session."""
    service = AuthService(db)
    return await service.register(body)


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Log in with email and password",
)
@limiter.limit(settings.RATE_LIMIT_STRICT)
async def login(request: Request, body: LoginRequest, db: DbSession) -> AuthResponse:
    """Authenticate a user and return a token pair."""
    service = AuthService(db)
    return await service.login(body)


@router.post(
    "/refresh",
    response_model=AuthResponse,
    summary="Rotate a refresh token",
)
@limiter.limit(settings.RATE_LIMIT_STRICT)
async def refresh(request: Request, body: RefreshRequest, db: DbSession) -> AuthResponse:
    """Exchange a refresh token for a new token pair (rotation)."""
    service = AuthService(db)
    return await service.refresh(body.refresh_token)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke all refresh tokens for the current user",
)
async def logout(db: DbSession, current_user: CurrentUser):
    """Log the user out of every device session."""
    service = AuthService(db)
    await service.logout(current_user.id)

@router.get(
    "/me",
    response_model=UserRead,
    summary="Return the authenticated user",
)
async def me(current_user: CurrentUser) -> UserRead:
    """Return the profile of the authenticated user."""
    return UserRead.model_validate(current_user)


@router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Change the current user's password",
)
async def change_password(
    db: DbSession,
    current_user: CurrentUser,
    body: ChangePasswordRequest,
):
    """Verify the current password and set a new one (revokes other sessions)."""
    service = AuthService(db)
    await service.change_password(current_user, body.current_password, body.new_password)
