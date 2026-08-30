"""Auth service: registration, login, refresh-token rotation, logout.

First-party email/password auth. Passwords are Argon2id-hashed; refresh
tokens are opaque, rotated on every refresh, and stored only as digests.
External identity-provider users (password_hash is NULL) cannot log in here.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.models.enums import UserRole
from app.models.organization import Organization
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.repositories.organization import OrganizationRepository
from app.repositories.refresh_token import RefreshTokenRepository
from app.repositories.user import UserRepository
from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest
from app.schemas.user import UserRead
from app.services.base import commit_with_retry, utcnow

logger = logging.getLogger("agencyos")


class AuthService:
    """Owns the auth transaction boundary (commit/rollback)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._orgs = OrganizationRepository(session)
        self._tokens = RefreshTokenRepository(session)

    # -- public API ------------------------------------------------------

    async def register(self, payload: RegisterRequest) -> AuthResponse:
        """Create an organization + owner and return a session token pair."""
        email = str(payload.email).strip().lower()
        await self._orgs.ensure_slug_available(payload.organization_slug)

        organization = Organization(name=payload.organization_name, slug=payload.organization_slug)
        self._orgs.add(organization)
        await self._session.flush()

        user = User(
            organization_id=organization.id,
            email=email,
            full_name=payload.full_name,
            role=UserRole.OWNER,
            password_hash=hash_password(payload.password),
        )
        self._users.add(user)

        try:
            await self._session.flush()
        except IntegrityError:
            await self._session.rollback()
            await self._resolve_register_conflict(email, payload.organization_slug)

        access, refresh, _record = await self._issue_tokens(user)
        await commit_with_retry(self._session)
        return await self._auth_response(user, access, refresh)

    async def login(self, payload: LoginRequest) -> AuthResponse:
        """Authenticate a user and return a session token pair."""
        email = str(payload.email).strip().lower()
        user = await self._users.get_active_by_email(email)
        if user is None or user.password_hash is None:
            raise self._invalid_credentials()
        if not verify_password(payload.password, user.password_hash):
            raise self._invalid_credentials()

        user.last_login_at = utcnow()
        access, refresh, _record = await self._issue_tokens(user)
        await commit_with_retry(self._session)
        return await self._auth_response(user, access, refresh)

    async def refresh(self, raw_token: str) -> AuthResponse:
        """Rotate a refresh token and issue a fresh token pair."""
        now = utcnow()
        record = await self._tokens.get_valid(hash_refresh_token(raw_token), now=now)
        if record is None:
            raise AppError(
                code="auth.invalid_refresh_token",
                message="Invalid or expired refresh token",
                status_code=401,
            )
        user = await self._users.get(record.user_id)
        if user is None or not user.is_active:
            raise AppError(
                code="auth.inactive_user",
                message="Account is disabled",
                status_code=403,
            )

        access, refresh, new_record = await self._issue_tokens(user)
        await self._tokens.mark_replaced(record.id, new_record.id, now=now)
        await commit_with_retry(self._session)
        return await self._auth_response(user, access, refresh)

    async def logout(self, user_id) -> None:
        """Revoke every outstanding refresh token for a user."""
        now = utcnow()
        await self._tokens.revoke_all_for_user(user_id, now=now)
        await commit_with_retry(self._session)

    async def change_password(self, user: User, current: str, new_password: str) -> None:
        """Verify the current password, then rotate to a new hash."""
        if user.password_hash is None or not verify_password(current, user.password_hash):
            raise AppError(
                code="auth.wrong_password",
                message="Current password is incorrect",
                status_code=400,
            )
        user.password_hash = hash_password(new_password)
        now = utcnow()
        await self._tokens.revoke_all_for_user(user.id, now=now)
        await commit_with_retry(self._session)

    async def _resolve_register_conflict(self, email: str, slug: str) -> None:
        """Distinguish email-vs-slug uniqueness conflicts and raise 409."""
        if await self._users.get_by_email(email) is not None:
            raise AppError(
                code="user.email_taken",
                message="A user with that email already exists",
                status_code=409,
            )
        if await self._orgs.get_by_slug(slug) is not None:
            raise AppError(
                code="organization.slug_taken",
                message="An organization with that slug already exists",
                status_code=409,
            )
        raise AppError(
            code="auth.register_failed",
            message="Could not create the account",
            status_code=409,
        )

    # -- internals -------------------------------------------------------

    async def _issue_tokens(self, user: User) -> tuple[str, str, RefreshToken]:
        """Create a refresh-token row and return (access, raw_refresh, record)."""
        raw_refresh = generate_refresh_token()
        record = RefreshToken(
            user_id=user.id,
            organization_id=user.organization_id,
            token_hash=hash_refresh_token(raw_refresh),
            expires_at=utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
        self._tokens.add(record)
        access = create_access_token(
            subject=str(user.id),
            extra_claims={"org": str(user.organization_id), "role": user.role},
        )
        return access, raw_refresh, record

    async def _auth_response(self, user: User, access: str, refresh: str) -> AuthResponse:
        # The user may carry expired attributes (e.g. updated_at refreshed by the
        # database on the preceding UPDATE). Reload so Pydantic serialization never
        # triggers an async lazy-load (which raises MissingGreenlet).
        await self._session.refresh(user)
        return AuthResponse(
            access_token=access,
            refresh_token=refresh,
            user=UserRead.model_validate(user),
        )

    @staticmethod
    def _invalid_credentials() -> AppError:
        return AppError(
            code="auth.invalid_credentials",
            message="Invalid email or password",
            status_code=401,
        )
