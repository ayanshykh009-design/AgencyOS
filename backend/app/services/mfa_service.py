"""MFA service: TOTP enrollment, activation, disable, and login challenge.

Enrollment is a two-step flow: ``enroll`` stores a *pending* secret (the user
must prove possession before it takes effect), and ``activate`` verifies a code
before flipping ``mfa_enabled`` on and issuing one-time recovery codes.

The login challenge is a short-lived JWT carrying ``scope = "mfa"``; the API
auth guard rejects that scope, so a challenge token can never be used as an
access token.
"""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.core.mfa import (
    decrypt_mfa_secret,
    encrypt_mfa_secret,
    generate_recovery_codes,
    generate_secret,
    provisioning_uri,
    verify_code,
)
from app.core.security import (
    create_access_token,
    hash_password,
    require_valid_token,
    verify_password,
)
from app.core.tenant_context import activate_org
from app.models.user import User
from app.models.user_recovery_code import UserRecoveryCode
from app.repositories.refresh_token import RefreshTokenRepository
from app.repositories.user import UserRepository
from app.repositories.user_recovery_code import UserRecoveryCodeRepository
from app.services.base import commit_with_retry, utcnow

logger = logging.getLogger("agencyos.mfa")

_MFA_CHALLENGE_SCOPE = "mfa"


class MfaService:
    """TOTP two-factor authentication lifecycle."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._codes = UserRecoveryCodeRepository(session)
        self._refresh_tokens = RefreshTokenRepository(session)

    # -- enrollment ------------------------------------------------------

    async def enroll(self, user: User) -> tuple[str, str]:
        """Create a pending secret. Returns ``(secret, otpauth_uri)``."""
        self._require_feature()
        if user.mfa_enabled:
            raise AppError(
                code="auth.mfa_already_enabled",
                message="Two-factor authentication is already enabled",
                status_code=409,
            )
        secret = generate_secret()
        user.mfa_secret_enc = encrypt_mfa_secret(secret)
        await commit_with_retry(self._session)
        uri = provisioning_uri(secret, account_name=user.email)
        return secret, uri

    async def activate(self, user: User, code: str) -> list[str]:
        """Verify a pending secret and enable MFA; returns recovery codes."""
        self._require_feature()
        if user.mfa_enabled:
            raise AppError(
                code="auth.mfa_already_enabled",
                message="Two-factor authentication is already enabled",
                status_code=409,
            )
        secret = self._pending_secret(user)
        if secret is None:
            raise AppError(
                code="auth.mfa_not_enrolled",
                message="Start enrollment before activating two-factor authentication",
                status_code=409,
            )
        if not verify_code(secret, code):
            raise self._invalid_code()
        user.mfa_enabled = True
        user.mfa_failed_attempts = 0
        user.mfa_locked_until = None
        await self._codes.delete_all_for_user(user.id)
        await self._revoke_all_sessions(user)
        recovery_codes = generate_recovery_codes()
        for raw in recovery_codes:
            self._codes.add(UserRecoveryCode(user_id=user.id, code_hash=hash_password(raw)))
        await commit_with_retry(self._session)
        logger.info("auth.mfa.enabled user_id=%s org_id=%s", user.id, user.organization_id)
        return recovery_codes

    async def disable(self, user: User, code: str) -> None:
        """Disable MFA after verifying the current factor (TOTP or recovery)."""
        self._require_feature()
        if not user.mfa_enabled:
            raise AppError(
                code="auth.mfa_not_enabled",
                message="Two-factor authentication is not enabled",
                status_code=409,
            )
        if not await self._verify_factor(user, code):
            raise self._invalid_code()
        user.mfa_enabled = False
        user.mfa_secret_enc = None
        user.mfa_failed_attempts = 0
        user.mfa_locked_until = None
        await self._codes.delete_all_for_user(user.id)
        await self._revoke_all_sessions(user)
        await commit_with_retry(self._session)
        logger.info("auth.mfa.disabled user_id=%s org_id=%s", user.id, user.organization_id)

    async def _revoke_all_sessions(self, user: User) -> None:
        """Invalidate every outstanding session for ``user``.

        Changing the second factor must not leave pre-existing sessions usable:
        a refresh token minted *before* MFA enrolment would otherwise keep
        rotating for up to ``REFRESH_TOKEN_EXPIRE_DAYS`` without ever presenting
        the new factor, which is an MFA bypass via an alternate auth path.
        Bumping ``token_version`` also kills already-issued access tokens
        server-side (enforced by the ``tv`` claim check in app/api/deps.py).
        """
        user.token_version = (user.token_version or 0) + 1
        await self._refresh_tokens.revoke_all_for_user(user.id, now=utcnow())

    # -- login challenge -------------------------------------------------

    def create_challenge(self, user: User) -> str:
        """Issue a short-lived MFA challenge token (never a usable access token)."""
        return create_access_token(
            subject=str(user.id),
            expires_minutes=settings.MFA_CHALLENGE_TTL_MINUTES,
            extra_claims={"scope": _MFA_CHALLENGE_SCOPE},
        )

    async def verify_challenge(self, mfa_token: str, code: str) -> User:
        """Validate a challenge token + second factor; returns the user."""
        self._require_feature()
        payload = require_valid_token(mfa_token)
        if payload.get("scope") != _MFA_CHALLENGE_SCOPE:
            raise self._invalid_challenge()
        try:
            user_id = uuid.UUID(payload["sub"])
        except (KeyError, ValueError, TypeError):
            raise self._invalid_challenge() from None
        user = await self._users.get_active_by_id_unscoped(user_id)
        if user is None or not user.is_active or not user.mfa_enabled:
            raise self._invalid_challenge()
        now = utcnow()
        if user.mfa_locked_until is not None and user.mfa_locked_until > now:
            retry_after = max(1, int((user.mfa_locked_until - now).total_seconds()))
            raise AppError(
                code="auth.mfa_locked",
                message="Too many incorrect codes. Try again later.",
                status_code=429,
                details={"retry_after": retry_after},
                headers={"Retry-After": str(retry_after)},
            )
        await activate_org(self._session, user.organization_id)
        if not await self._verify_factor(user, code):
            self._register_failed_attempt(user, now)
            await commit_with_retry(self._session)
            raise self._invalid_code()
        user.mfa_failed_attempts = 0
        user.mfa_locked_until = None
        await commit_with_retry(self._session)
        return user

    # -- internals -------------------------------------------------------

    async def _verify_factor(self, user: User, code: str) -> bool:
        """Accept a valid TOTP code or consume a matching recovery code."""
        secret = self._pending_secret(user)
        if secret is not None and verify_code(secret, code):
            return True
        return await self._consume_recovery_code(user, code)

    async def _consume_recovery_code(self, user: User, code: str) -> bool:
        cleaned = code.strip().upper()
        if not cleaned:
            return False
        for record in await self._codes.list_unused(user.id):
            if verify_password(cleaned, record.code_hash):
                claimed = await self._codes.mark_used(record.id, now=utcnow())
                if claimed:
                    return True
        return False

    @staticmethod
    def _pending_secret(user: User) -> str | None:
        if not user.mfa_secret_enc:
            return None
        try:
            return decrypt_mfa_secret(user.mfa_secret_enc)
        except Exception:  # noqa: BLE001 - corrupted/foreign key material
            logger.error("auth.mfa.secret_decrypt_failed user_id=%s", user.id)
            return None

    @staticmethod
    def _register_failed_attempt(user: User, now) -> None:
        user.mfa_failed_attempts = (user.mfa_failed_attempts or 0) + 1
        over = user.mfa_failed_attempts - settings.MFA_MAX_ATTEMPTS
        if over >= 0:
            delay = min(30 * (2 ** min(over, 10)), 900)
            user.mfa_locked_until = now + timedelta(seconds=delay)

    @staticmethod
    def _require_feature() -> None:
        if not settings.MFA_ENABLED:
            raise AppError(
                code="auth.mfa_unavailable",
                message="Two-factor authentication is not enabled for this deployment",
                status_code=404,
            )

    @staticmethod
    def _invalid_code() -> AppError:
        return AppError(
            code="auth.invalid_mfa_code",
            message="Invalid authentication code",
            status_code=401,
        )

    @staticmethod
    def _invalid_challenge() -> AppError:
        return AppError(
            code="auth.invalid_mfa_token",
            message="Invalid or expired MFA challenge",
            status_code=401,
        )
