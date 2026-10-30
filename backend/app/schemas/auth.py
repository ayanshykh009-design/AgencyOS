"""Auth API schemas: registration, login, token refresh.

Phase 2 implements first-party email/password auth backed by the JWT
primitives in ``app/core/security.py`` and rotation-based refresh tokens.
"""

from pydantic import BaseModel, EmailStr, Field

from app.core.config import settings
from app.schemas.user import UserRead


class LoginRequest(BaseModel):
    """User credentials for login."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class RegisterRequest(BaseModel):
    """Payload to create a new organization and its owner account."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=255)
    organization_name: str = Field(min_length=1, max_length=255)
    organization_slug: str = Field(min_length=1, max_length=63, pattern=r"^[a-z0-9][a-z0-9-]*$")


class TokenResponse(BaseModel):
    """Access token returned after login/refresh.

    The refresh token is delivered exclusively through the HttpOnly
    ``agencyos.refresh`` cookie (V5 Option B) and is never serialized
    into a JSON response body.
    """

    access_token: str
    token_type: str = "bearer"
    # Reflect the configured access-token lifetime instead of a hardcoded value,
    # so clients never trust a stale "expires_in" after a config change.
    expires_in: int = Field(
        default_factory=lambda: settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


class AuthResponse(TokenResponse):
    """Token pair plus the authenticated user (avoids an extra round trip)."""

    user: UserRead
    # True when the account must confirm its email before the session can be
    # used for protected actions; the login gate enforces the same condition.
    email_verification_required: bool = False
    # Non-production only: the raw verification link (never returned in prod).
    dev_email_verification_url: str | None = None


class RefreshRequest(BaseModel):
    """Empty body: the refresh token travels in the HttpOnly cookie.

    Retained as a model so the endpoint keeps a documented request schema;
    no refresh-token field is accepted in the body (cookie-only, V5).
    """

    pass


class ChangePasswordRequest(BaseModel):
    """Payload to change the current user's password."""

    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class VerifyEmailRequest(BaseModel):
    """Payload to confirm an email address with a verification token."""

    token: str = Field(min_length=1)


class VerifyEmailResendRequest(BaseModel):
    """Payload to request a fresh verification link by email (pre-auth)."""

    email: EmailStr


class MessageResponse(BaseModel):
    """Generic acknowledgement (optionally carrying a development/test-only link)."""

    detail: str
    dev_url: str | None = None


class PasswordResetRequest(BaseModel):
    """Payload to request a password reset (enumeration-safe)."""

    email: EmailStr


class PasswordResetConfirmRequest(BaseModel):
    """Payload to complete a password reset with a token + new password."""

    token: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=128)


class MfaEnrollResponse(BaseModel):
    """Pending TOTP enrollment material (secret + provisioning URI)."""

    secret: str
    otpauth_url: str


class MfaCodeRequest(BaseModel):
    """A TOTP (or recovery) code submitted to a MFA endpoint."""

    code: str = Field(min_length=1, max_length=64)


class MfaActivateResponse(BaseModel):
    """Recovery codes returned once, at activation time."""

    recovery_codes: list[str]


class MfaVerifyRequest(BaseModel):
    """Second-factor submission to complete a MFA-gated login."""

    mfa_token: str = Field(min_length=1)
    code: str = Field(min_length=1, max_length=64)
