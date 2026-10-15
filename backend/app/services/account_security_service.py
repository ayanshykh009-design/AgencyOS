"""Account-lifecycle security: email verification + password reset.

Both flows issue single-use, hashed, short-lived tokens stored in
``auth_tokens`` and delivered by email. The flows are pre-authentication (the
token is presented with no session), so token/user resolution goes through the
SECURITY DEFINER lookups and then binds the tenant context before any write.

Password reset revokes every outstanding session (``token_version`` bump +
refresh-token revocation), so a compromised session cannot survive a reset.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.email import send_email
from app.core.errors import AppError
from app.core.security import (
    generate_opaque_token,
    hash_opaque_token,
    hash_password,
    verify_password_dummy,
)
from app.core.tenant_context import activate_org
from app.models.auth_token import (
    PURPOSE_EMAIL_VERIFICATION,
    PURPOSE_PASSWORD_RESET,
    AuthToken,
)
from app.models.user import User
from app.repositories.auth_token import AuthTokenRepository
from app.repositories.refresh_token import RefreshTokenRepository
from app.repositories.user import UserRepository
from app.services.base import commit_with_retry, utcnow

logger = logging.getLogger("agencyos.account_security")


class AccountSecurityService:
    """Email-verification and password-reset token lifecycle."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._tokens = AuthTokenRepository(session)
        self._refresh_tokens = RefreshTokenRepository(session)

    # -- email verification ---------------------------------------------

    def create_verification_token(self, user: User) -> str:
        """Add a verification token row (caller owns the commit). Returns raw."""
        return self._create_token(user, PURPOSE_EMAIL_VERIFICATION)

    def verification_url(self, raw_token: str) -> str:
        return f"{settings.FRONTEND_URL}/verify-email?token={raw_token}"

    def dev_verification_url(self, raw_token: str) -> str | None:
        """Verification link surfaced only outside production."""
        return self._dev_url(self.verification_url(raw_token))

    async def send_verification_email(self, user: User, raw_token: str) -> None:
        url = self.verification_url(raw_token)
        send_email(
            to=user.email,
            subject="Verify your AgencyOS email",
            body=(
                "Welcome to AgencyOS.\n\n"
                f"Confirm your email address: {url}\n\n"
                "If you did not create this account you can ignore this message."
            ),
        )

    async def verify_email(self, raw_token: str) -> None:
        """Confirm ownership of an email address via a verification token."""
        now = utcnow()
        record = self._usable(
            await self._tokens.get_by_hash_any(hash_opaque_token(raw_token)),
            PURPOSE_EMAIL_VERIFICATION,
            now,
        )
        if record is None:
            raise self._invalid_verification()
        user = await self._users.get_active_by_id_unscoped(record.user_id)
        if user is None or not user.is_active:
            raise self._invalid_verification()
        await activate_org(self._session, user.organization_id)
        user.email_verified_at = now
        user.email_verification_required = False
        await self._tokens.mark_used(record.id, now=now)
        await commit_with_retry(self._session)
        logger.info(
            "auth.email_verified user_id=%s org_id=%s", user.id, user.organization_id
        )

    async def resend_verification(self, user: User) -> str | None:
        """Re-issue a verification token, invalidating any previous one."""
        now = utcnow()
        await self._tokens.invalidate_outstanding(
            user.id, PURPOSE_EMAIL_VERIFICATION, now=now
        )
        raw_token = self._create_token(user, PURPOSE_EMAIL_VERIFICATION)
        await commit_with_retry(self._session)
        await self.send_verification_email(user, raw_token)
        return self._dev_url(self.verification_url(raw_token))

    # -- password reset --------------------------------------------------

    def reset_url(self, raw_token: str) -> str:
        return f"{settings.FRONTEND_URL}/reset-password?token={raw_token}"

    async def request_password_reset(self, email: str) -> str | None:
        """Issue a reset token for ``email`` if an account exists.

        Never reveals whether the account exists (the endpoint always returns
        202); the caller must not branch on the result beyond dev linking.
        """
        now = utcnow()
        user = await self._users.get_active_by_email(email)
        if user is None or user.password_hash is None:
            # Burn comparable CPU so timing does not leak account existence.
            verify_password_dummy("agencyos-reset-timing")
            self._log_reset(email, found=False)
            return None
        await activate_org(self._session, user.organization_id)
        await self._tokens.invalidate_outstanding(
            user.id, PURPOSE_PASSWORD_RESET, now=now
        )
        raw_token = self._create_token(user, PURPOSE_PASSWORD_RESET)
        await commit_with_retry(self._session)
        url = self.reset_url(raw_token)
        send_email(
            to=user.email,
            subject="Reset your AgencyOS password",
            body=(
                "A password reset was requested for your AgencyOS account.\n\n"
                f"Choose a new password: {url}\n\n"
                "This link expires shortly and can be used once. If you did not "
                "request it, no action is needed and your password is unchanged."
            ),
        )
        self._log_reset(email, found=True)
        return self._dev_url(url)

    async def reset_password(self, raw_token: str, new_password: str) -> None:
        """Consume a reset token, set the new password, revoke all sessions."""
        now = utcnow()
        record = self._usable(
            await self._tokens.get_by_hash_any(hash_opaque_token(raw_token)),
            PURPOSE_PASSWORD_RESET,
            now,
        )
        if record is None:
            raise self._invalid_reset()
        user = await self._users.get_active_by_id_unscoped(record.user_id)
        if user is None or not user.is_active:
            raise self._invalid_reset()
        await activate_org(self._session, user.organization_id)
        user.password_hash = hash_password(new_password)
        user.token_version = (user.token_version or 0) + 1
        user.failed_login_attempts = 0
        user.locked_until = None
        await self._refresh_tokens.revoke_all_for_user(user.id, now=now)
        await self._tokens.mark_used(record.id, now=now)
        await commit_with_retry(self._session)
        logger.info(
            "auth.password_reset user_id=%s org_id=%s", user.id, user.organization_id
        )

    # -- internals -------------------------------------------------------

    def _create_token(self, user: User, purpose: str) -> str:
        raw_token = generate_opaque_token()
        if purpose == PURPOSE_EMAIL_VERIFICATION:
            ttl = timedelta(minutes=settings.EMAIL_VERIFICATION_TOKEN_TTL_MINUTES)
        else:
            ttl = timedelta(minutes=settings.PASSWORD_RESET_TOKEN_TTL_MINUTES)
        self._tokens.add(
            AuthToken(
                user_id=user.id,
                purpose=purpose,
                token_hash=hash_opaque_token(raw_token),
                expires_at=utcnow() + ttl,
            )
        )
        return raw_token

    @staticmethod
    def _usable(
        record: AuthToken | None, purpose: str, now
    ) -> AuthToken | None:
        """Return the token only if it is the right purpose, unused and live."""
        if (
            record is None
            or record.purpose != purpose
            or record.used_at is not None
            or record.expires_at <= now
        ):
            return None
        return record

    @staticmethod
    def _dev_url(url: str) -> str | None:
        """Surface the raw link only outside production (dev/test convenience)."""
        return None if settings.APP_ENV == "production" else url

    @staticmethod
    def _invalid_verification() -> AppError:
        return AppError(
            code="auth.invalid_verification_token",
            message="Invalid or expired verification link",
            status_code=400,
        )

    @staticmethod
    def _invalid_reset() -> AppError:
        return AppError(
            code="auth.invalid_reset_token",
            message="Invalid or expired password reset link",
            status_code=400,
        )

    @staticmethod
    def _log_reset(email: str, *, found: bool) -> None:
        from hashlib import sha256

        digest = sha256(email.strip().lower().encode("utf-8")).hexdigest()[:16]
        logger.info("auth.password_reset.request email_digest=%s found=%s", digest, found)
