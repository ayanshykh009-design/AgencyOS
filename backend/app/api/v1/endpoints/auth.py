"""Authentication endpoints: register, login, refresh, logout, me.

Layered flow: this router -> app/services/auth_service.py -> repositories.

NOTE: intentionally does NOT use ``from __future__ import annotations``.
slowapi's ``functools.wraps`` copies string annotations and FastAPI then
resolves them against slowapi's globals, producing unresolved ForwardRefs.
Real (non-string) annotations keep ``get_type_hints`` working.
"""

from fastapi import APIRouter, Request, Response, status

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.core.errors import AppError
from app.core.rate_limit import limiter
from app.schemas.auth import (
    AuthResponse,
    ChangePasswordRequest,
    LoginRequest,
    MessageResponse,
    MfaActivateResponse,
    MfaCodeRequest,
    MfaEnrollResponse,
    MfaVerifyRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    RegisterRequest,
    VerifyEmailRequest,
    VerifyEmailResendRequest,
)
from app.schemas.user import UserRead
from app.services.account_security_service import AccountSecurityService
from app.services.auth_service import AuthService
from app.services.mfa_service import MfaService

router = APIRouter()


def _validate_csrf_origin(request: Request, require: bool = True) -> None:
    """Validate the Origin/Referer of browser requests against trusted origins.

    Used for cookie-authenticated state-changing endpoints (refresh, logout).
    When ``require`` is True (refresh), a missing/invalid origin is rejected.
    When False (logout, which also accepts a Bearer token), validation runs
    only when an Origin/Referer is present.
    """
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")
    allowed = set(settings.cors_origins_list)

    candidate: str | None = None
    if origin:
        candidate = origin
    elif referer:
        # Extract origin from Referer URL.
        try:
            from urllib.parse import urlparse

            parsed = urlparse(referer)
            if parsed.scheme and parsed.netloc:
                candidate = f"{parsed.scheme}://{parsed.netloc}"
        except Exception:  # noqa: BLE001
            candidate = None

    if candidate is None:
        if require:
            raise AppError(
                code="auth.csrf_origin_required",
                message="Origin header is required",
                status_code=403,
            )
        return
    if candidate not in allowed:
        raise AppError(
            code="auth.csrf_origin_invalid",
            message="Origin not allowed",
            status_code=403,
        )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        path=settings.REFRESH_COOKIE_PATH,
    )


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register an organization and its owner",
)
@limiter.limit(settings.RATE_LIMIT_STRICT)
async def register(
    request: Request, body: RegisterRequest, db: DbSession, response: Response
) -> AuthResponse:
    """Create a new organization + owner account and return a session."""
    service = AuthService(db)
    return await service.register(body, response=response)


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Log in with email and password",
)
@limiter.limit(settings.RATE_LIMIT_STRICT)
async def login(
    request: Request, body: LoginRequest, db: DbSession, response: Response
) -> AuthResponse:
    """Authenticate a user and return a token pair."""
    service = AuthService(db)
    return await service.login(body, response=response)


@router.post(
    "/refresh",
    response_model=AuthResponse,
    summary="Rotate a refresh token",
)
@limiter.limit(settings.RATE_LIMIT_STRICT)
async def refresh(request: Request, db: DbSession, response: Response) -> AuthResponse:
    """Exchange the HttpOnly refresh cookie for a new token pair (rotation)."""
    _validate_csrf_origin(request)
    raw_token = request.cookies.get(settings.REFRESH_COOKIE_NAME)
    if not raw_token:
        raise AppError(
            code="auth.invalid_refresh", message="Missing refresh token", status_code=401
        )
    service = AuthService(db)
    return await service.refresh(raw_token, response=response)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke all sessions for the current user",
)
@limiter.limit(settings.RATE_LIMIT_STRICT)
async def logout(request: Request, db: DbSession, current_user: CurrentUser, response: Response):
    """Log the user out of every device session (revokes access + refresh)."""
    _validate_csrf_origin(request, require=False)
    service = AuthService(db)
    await service.logout(current_user)
    _clear_refresh_cookie(response)


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
@limiter.limit(settings.RATE_LIMIT_STRICT)
async def change_password(
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
    body: ChangePasswordRequest,
):
    """Verify the current password and set a new one (revokes all sessions)."""
    service = AuthService(db)
    await service.change_password(current_user, body.current_password, body.new_password)


# -- Email verification -----------------------------------------------------


@router.post(
    "/verify-email",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Confirm an email address with a verification token",
)
@limiter.limit(settings.RATE_LIMIT_STRICT)
async def verify_email(request: Request, body: VerifyEmailRequest, db: DbSession):
    """Consume a single-use verification token and mark the account verified."""
    await AccountSecurityService(db).verify_email(body.token)


@router.post(
    "/verify-email/resend",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=MessageResponse,
    summary="Re-send the email-verification link",
)
@limiter.limit(settings.RATE_LIMIT_STRICT)
async def resend_verification(
    request: Request, db: DbSession, body: VerifyEmailResendRequest
) -> MessageResponse:
    """Invalidate the previous token and send a fresh verification link.

    Pre-authentication: does not require an authenticated session, so
    unverified users blocked by the verification gate can still request a
    new link. Enumeration-safe (always 202).
    """
    if not settings.EMAIL_VERIFICATION_ENABLED:
        return MessageResponse(detail="Email verification is not enabled")
    account = AccountSecurityService(db)
    dev_url = await account.resend_verification_by_email(str(body.email))
    return MessageResponse(detail="Verification email sent", dev_url=dev_url)


# -- Password reset ---------------------------------------------------------


@router.post(
    "/password-reset/request",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=MessageResponse,
    summary="Request a password reset email",
)
@limiter.limit(settings.RATE_LIMIT_STRICT)
async def password_reset_request(
    request: Request, body: PasswordResetRequest, db: DbSession
) -> MessageResponse:
    """Always 202: never reveals whether an account exists (enumeration-safe)."""
    if not settings.PASSWORD_RESET_ENABLED:
        return MessageResponse(detail="Password reset is not enabled")
    dev_url = await AccountSecurityService(db).request_password_reset(str(body.email))
    return MessageResponse(detail="If that account exists, a reset email was sent", dev_url=dev_url)


@router.post(
    "/password-reset/confirm",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Complete a password reset with a token",
)
@limiter.limit(settings.RATE_LIMIT_STRICT)
async def password_reset_confirm(
    request: Request, body: PasswordResetConfirmRequest, db: DbSession
):
    """Set a new password and revoke every existing session for the account."""
    await AccountSecurityService(db).reset_password(body.token, body.new_password)


# -- Two-factor authentication ----------------------------------------------


@router.post(
    "/mfa/enroll",
    response_model=MfaEnrollResponse,
    summary="Start TOTP enrollment (pending until a code is confirmed)",
)
@limiter.limit(settings.RATE_LIMIT_STRICT)
async def mfa_enroll(
    request: Request, db: DbSession, current_user: CurrentUser
) -> MfaEnrollResponse:
    """Generate a pending TOTP secret and provisioning URI."""
    secret, uri = await MfaService(db).enroll(current_user)
    return MfaEnrollResponse(secret=secret, otpauth_url=uri)


@router.post(
    "/mfa/activate",
    response_model=MfaActivateResponse,
    summary="Confirm enrollment and enable TOTP two-factor authentication",
)
@limiter.limit(settings.RATE_LIMIT_STRICT)
async def mfa_activate(
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
    body: MfaCodeRequest,
) -> MfaActivateResponse:
    """Verify a code against the pending secret and return recovery codes."""
    codes = await MfaService(db).activate(current_user, body.code)
    return MfaActivateResponse(recovery_codes=codes)


@router.post(
    "/mfa/disable",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Disable TOTP two-factor authentication",
)
@limiter.limit(settings.RATE_LIMIT_STRICT)
async def mfa_disable(
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
    body: MfaCodeRequest,
):
    """Verify the current factor, then turn off TOTP and drop recovery codes."""
    await MfaService(db).disable(current_user, body.code)


@router.post(
    "/mfa/verify",
    response_model=AuthResponse,
    summary="Complete a MFA-gated login",
)
@limiter.limit(settings.RATE_LIMIT_STRICT)
async def mfa_verify(
    request: Request, body: MfaVerifyRequest, db: DbSession, response: Response
) -> AuthResponse:
    """Validate the challenge token + second factor, then issue a session."""
    user = await MfaService(db).verify_challenge(body.mfa_token, body.code)
    return await AuthService(db).session_for_user(user, response=response)
