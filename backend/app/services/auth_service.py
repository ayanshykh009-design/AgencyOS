"""Auth service: registration, login, refresh-token rotation, logout.

First-party email/password auth. Passwords are Argon2id-hashed; refresh
tokens are opaque, rotated on every refresh, and stored only as digests.
External identity-provider users (password_hash is NULL) cannot log in here.
"""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from hashlib import sha256

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
    verify_password_dummy,
)
from app.core.tenant_context import activate_org
from app.models.enums import UserRole
from app.models.organization import Organization
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.repositories.organization import OrganizationRepository
from app.repositories.refresh_token import RefreshTokenRepository
from app.repositories.user import UserRepository
from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest
from app.schemas.user import UserRead
from app.services.account_security_service import AccountSecurityService
from app.services.base import commit_with_retry, utcnow
from app.services.mfa_service import MfaService

logger = logging.getLogger("agencyos.auth")

# Per-account brute-force throttle. Only *incorrect* passwords are throttled;
# a correct password always authenticates (see ``login``), so an attacker can
# never lock a legitimate user out of their own account.
_LOGIN_MAX_ATTEMPTS = 5
_LOGIN_LOCK_BASE_SECONDS = 30
_LOGIN_LOCK_MAX_SECONDS = 900


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

        # Assign the id explicitly: the ORM ``default=uuid.uuid4`` only fires at
        # flush time, but the tenant GUC must be bound BEFORE the first INSERT
        # so the RLS ``WITH CHECK (id = tenant_org_id())`` can hold.
        organization = Organization(
            id=uuid.uuid4(),
            name=payload.organization_name,
            slug=payload.organization_slug,
        )
        await activate_org(self._session, organization.id)
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

        # New accounts may be required to prove email ownership (opt-in per
        # deployment). The token row is created in the same transaction as the
        # account; the email is sent after commit.
        account = AccountSecurityService(self._session)
        verification_token: str | None = None
        if settings.EMAIL_VERIFICATION_ENABLED:
            user.email_verification_required = True
            verification_token = account.create_verification_token(user)

        access, refresh, _record = await self._issue_tokens(user)
        await commit_with_retry(self._session)
        dev_url: str | None = None
        if verification_token is not None:
            await account.send_verification_email(user, verification_token)
            dev_url = account.dev_verification_url(verification_token)
        return await self._auth_response(user, access, refresh, dev_verification_url=dev_url)

    async def login(self, payload: LoginRequest) -> AuthResponse:
        """Authenticate a user and return a session token pair.

        Timing-safe for unknown accounts and victim-safe under brute force: a
        correct password always authenticates, while repeated *incorrect* guesses
        escalate a progressive per-account lock (429 + ``Retry-After``).
        """
        email = str(payload.email).strip().lower()
        user = await self._users.get_active_by_email(email)
        if user is None or user.password_hash is None:
            # Same CPU cost as a real check so account existence is not leaked.
            verify_password_dummy(payload.password)
            self._log_login_failure(email, reason="unknown_account")
            raise self._invalid_credentials()

        now = utcnow()
        password_ok = verify_password(payload.password, user.password_hash)
        if not password_ok:
            # A locked account only rejects incorrect guesses; the correct
            # password path below still runs, so a victim is never locked out.
            if user.locked_until is not None and user.locked_until > now:
                self._log_login_failure(email, reason="locked")
                raise self._account_locked(user.locked_until, now)
            await activate_org(self._session, user.organization_id)
            self._register_failed_attempt(user, now)
            await commit_with_retry(self._session)
            self._log_login_failure(email, reason="bad_password")
            raise self._invalid_credentials()

        # Correct password: evaluate account-setup gates before issuing tokens.
        # Email verification (when the deployment requires it) and any enrolled
        # second factor must be satisfied first.
        if user.email_verification_required and user.email_verified_at is None:
            raise self._email_verification_required()
        if user.mfa_enabled:
            raise self._mfa_required(MfaService(self._session).create_challenge(user))

        # Correct password: clear any accumulated throttle state.
        # Bind the tenant context before any write: RLS would otherwise reject
        # the users UPDATE and the refresh_tokens INSERT (org-scoped WITH CHECK)
        # because no org GUC is set yet.
        await activate_org(self._session, user.organization_id)
        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login_at = now
        access, refresh, _record = await self._issue_tokens(user)
        await commit_with_retry(self._session)
        logger.info(
            "auth.login.success user_id=%s org_id=%s", user.id, user.organization_id
        )
        return await self._auth_response(user, access, refresh)

    async def refresh(self, raw_token: str) -> AuthResponse:
        """Rotate a refresh token and issue a fresh token pair.

        Detects token *reuse*: if the presented token was already rotated
        (revoked), it has leaked, so the entire token family and every access
        token for the user are revoked and the caller must re-authenticate.
        """
        now = utcnow()
        record = await self._tokens.get_any(hash_refresh_token(raw_token))
        if record is None:
            raise self._invalid_refresh()
        if record.revoked_at is not None:
            await self._on_reuse_detected(record, now)
        if record.expires_at <= now:
            raise self._invalid_refresh()
        # The definer lookup returns the token's org, which lets us bind the
        # tenant context before the (RLS-scoped) users SELECT below.
        await activate_org(self._session, record.organization_id)
        user = await self._users.get(record.user_id)
        if user is None or not user.is_active:
            raise AppError(
                code="auth.inactive_user",
                message="Account is disabled",
                status_code=403,
            )

        access, refresh, new_record = await self._issue_tokens(
            user, family_id=record.family_id
        )
        await self._tokens.mark_replaced(record.id, new_record.id, now=now)
        await commit_with_retry(self._session)
        return await self._auth_response(user, access, refresh)

    async def logout(self, user: User) -> None:
        """Revoke every outstanding refresh token and access token for a user."""
        user.token_version = (user.token_version or 0) + 1
        await self._tokens.revoke_all_for_user(user.id, now=utcnow())
        await commit_with_retry(self._session)
        logger.info("auth.logout user_id=%s org_id=%s", user.id, user.organization_id)

    async def session_for_user(self, user: User) -> AuthResponse:
        """Issue a token pair for an already-authenticated user (e.g. post-MFA).

        Used to complete a login that was gated on a second factor: the user
        identity is established, but tokens are only minted here.
        """
        access, refresh, _record = await self._issue_tokens(user)
        await commit_with_retry(self._session)
        return await self._auth_response(user, access, refresh)

    async def change_password(self, user: User, current: str, new_password: str) -> None:
        """Verify the current password, then rotate to a new hash.

        Bumps ``token_version`` so every previously issued access token (on all
        devices, including the caller's) is revoked immediately.
        """
        if user.password_hash is None or not verify_password(current, user.password_hash):
            raise AppError(
                code="auth.wrong_password",
                message="Current password is incorrect",
                status_code=400,
            )
        user.password_hash = hash_password(new_password)
        user.token_version = (user.token_version or 0) + 1
        now = utcnow()
        await self._tokens.revoke_all_for_user(user.id, now=now)
        await commit_with_retry(self._session)
        logger.info(
            "auth.password_changed user_id=%s org_id=%s", user.id, user.organization_id
        )

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

    async def _issue_tokens(
        self, user: User, *, family_id: uuid.UUID | None = None
    ) -> tuple[str, str, RefreshToken]:
        """Create a refresh-token row and return (access, raw_refresh, record).

        ``family_id`` is inherited on rotation so reuse detection can revoke the
        whole session chain; a fresh login/register starts a new family.
        """
        raw_refresh = generate_refresh_token()
        record = RefreshToken(
            user_id=user.id,
            organization_id=user.organization_id,
            token_hash=hash_refresh_token(raw_refresh),
            family_id=family_id or uuid.uuid4(),
            expires_at=utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
        self._tokens.add(record)
        access = create_access_token(
            subject=str(user.id),
            extra_claims={"org": str(user.organization_id), "role": user.role},
            token_version=user.token_version or 0,
        )
        return access, raw_refresh, record

    async def _auth_response(
        self,
        user: User,
        access: str,
        refresh: str,
        *,
        dev_verification_url: str | None = None,
    ) -> AuthResponse:
        # The user may carry expired attributes (e.g. updated_at refreshed by the
        # database on the preceding UPDATE). Reload so Pydantic serialization never
        # triggers an async lazy-load (which raises MissingGreenlet).
        await self._session.refresh(user)
        return AuthResponse(
            access_token=access,
            refresh_token=refresh,
            user=UserRead.model_validate(user),
            email_verification_required=bool(
                user.email_verification_required and user.email_verified_at is None
            ),
            dev_email_verification_url=dev_verification_url,
        )

    @staticmethod
    def _invalid_credentials() -> AppError:
        return AppError(
            code="auth.invalid_credentials",
            message="Invalid email or password",
            status_code=401,
        )

    @staticmethod
    def _email_verification_required() -> AppError:
        return AppError(
            code="auth.email_verification_required",
            message="Confirm your email address before signing in",
            status_code=403,
        )

    @staticmethod
    def _mfa_required(challenge: str) -> AppError:
        return AppError(
            code="auth.mfa_required",
            message="A second authentication factor is required",
            status_code=401,
            details={"mfa_token": challenge},
        )

    @staticmethod
    def _invalid_refresh() -> AppError:
        return AppError(
            code="auth.invalid_refresh_token",
            message="Invalid or expired refresh token",
            status_code=401,
        )

    async def _on_reuse_detected(self, record: RefreshToken, now) -> None:
        """Revoke the leaked token family and kill the user's access tokens."""
        await activate_org(self._session, record.organization_id)
        user = await self._users.get(record.user_id)
        revoked = await self._tokens.revoke_family(record.family_id, now=now)
        if user is not None:
            user.token_version = (user.token_version or 0) + 1
        await commit_with_retry(self._session)
        logger.warning(
            "auth.refresh.reuse_detected user_id=%s family_id=%s revoked=%s",
            record.user_id,
            record.family_id,
            revoked,
        )
        raise AppError(
            code="auth.refresh_token_reuse",
            message="Refresh token reuse detected; all sessions were revoked",
            status_code=401,
        )

    @staticmethod
    def _register_failed_attempt(user: User, now) -> None:
        """Increment the failure counter and apply progressive lockout.

        Lock duration doubles per attempt past the threshold (capped), giving an
        attacker diminishing returns without ever affecting a correct password.
        """
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
        over = user.failed_login_attempts - _LOGIN_MAX_ATTEMPTS
        if over >= 0:
            delay = min(_LOGIN_LOCK_BASE_SECONDS * (2 ** min(over, 10)), _LOGIN_LOCK_MAX_SECONDS)
            user.locked_until = now + timedelta(seconds=delay)

    @staticmethod
    def _account_locked(locked_until, now) -> AppError:
        retry_after = max(1, int((locked_until - now).total_seconds()))
        return AppError(
            code="auth.too_many_attempts",
            message="Too many failed login attempts. Try again later.",
            status_code=429,
            details={"retry_after": retry_after},
            headers={"Retry-After": str(retry_after)},
        )

    @staticmethod
    def _log_login_failure(email: str, *, reason: str) -> None:
        # Digest the email rather than logging PII; corr with request id upstream.
        digest = sha256(email.encode("utf-8")).hexdigest()[:16]
        logger.warning("auth.login.failure email_digest=%s reason=%s", digest, reason)
