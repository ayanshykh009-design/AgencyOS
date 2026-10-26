"""Unit tests for email verification, password reset, and TOTP MFA.

These are the account-lifecycle and second-factor services added for the
authentication hardening pass. Like the rest of the unit suite, they swap the
concrete repositories for lightweight fakes so the business rules are verified
without a database.
"""
import uuid
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.errors import AppError
from app.core.mfa import decrypt_mfa_secret, generate_secret
from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.models.auth_token import (
    PURPOSE_EMAIL_VERIFICATION,
    PURPOSE_PASSWORD_RESET,
    AuthToken,
)
from app.models.enums import UserRole
from app.models.user import User
from app.models.user_recovery_code import UserRecoveryCode
from app.services.account_security_service import AccountSecurityService
from app.services.base import utcnow
from app.services.mfa_service import MfaService

ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


class FakeSession:
    """Minimal async session: records adds; flush/commit are no-ops."""

    def __init__(self, *, fail_on_flush: int = 0) -> None:
        self.added: list[object] = []
        self.committed = False
        self._flush_count = 0
        self._fail_on = fail_on_flush

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        self._flush_count += 1
        if self._flush_count == self._fail_on:
            raise IntegrityError("flush()", {}, Exception("constraint violation"))

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        return None

    async def refresh(self, instance: object) -> None:
        return None

    async def execute(self, *args: object, **kwargs: object) -> None:
        return None


def _make_user(**overrides: object) -> User:
    user = User(
        organization_id=ORG_ID,
        email="owner@example.com",
        full_name="Owner",
        role=UserRole.OWNER,
        password_hash=hash_password("S3cure!pass"),
    )
    user.id = uuid.uuid4()
    user.created_at = utcnow()
    user.updated_at = utcnow()
    user.is_active = True
    user.token_version = 0
    user.failed_login_attempts = 0
    user.locked_until = None
    user.email_verified_at = None
    user.email_verification_required = False
    user.mfa_enabled = False
    user.mfa_secret_enc = None
    user.mfa_failed_attempts = 0
    user.mfa_locked_until = None
    for key, value in overrides.items():
        setattr(user, key, value)
    return user


def _auth_token(**overrides: object) -> AuthToken:
    token = AuthToken(
        user_id=uuid.uuid4(),
        purpose=PURPOSE_EMAIL_VERIFICATION,
        token_hash="deadbeef",
        expires_at=utcnow() + timedelta(minutes=15),
    )
    token.id = uuid.uuid4()
    token.created_at = utcnow()
    for key, value in overrides.items():
        setattr(token, key, value)
    return token


# ---------------------------------------------------------------------------
# Email verification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_email_marks_user_verified_and_consumes_token() -> None:
    session = FakeSession()
    service = AccountSecurityService(session)
    service._users = MagicMock()
    service._tokens = MagicMock()
    user = _make_user()
    user.email_verification_required = True
    token = _auth_token(user_id=user.id)
    service._tokens.get_by_hash_any = AsyncMock(return_value=token)
    service._users.get_active_by_id_unscoped = AsyncMock(return_value=user)
    service._tokens.claim = AsyncMock(return_value=True)

    await service.verify_email("a-valid-raw-token")

    assert user.email_verified_at is not None
    assert user.email_verification_required is False
    service._tokens.claim.assert_awaited_once()
    assert session.committed is True


@pytest.mark.asyncio
async def test_verify_email_rejects_unknown_token() -> None:
    session = FakeSession()
    service = AccountSecurityService(session)
    service._tokens = MagicMock()
    service._tokens.get_by_hash_any = AsyncMock(return_value=None)

    with pytest.raises(AppError) as exc_info:
        await service.verify_email("an-unknown-token")

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "auth.invalid_verification_token"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda t: setattr(t, "used_at", utcnow()), id="already-used"),
        pytest.param(
            lambda t: setattr(t, "expires_at", utcnow() - timedelta(minutes=1)),
            id="expired",
        ),
        pytest.param(
            lambda t: setattr(t, "purpose", PURPOSE_PASSWORD_RESET), id="wrong-purpose"
        ),
    ],
)
async def test_verify_email_rejects_unusable_token(mutate) -> None:
    session = FakeSession()
    service = AccountSecurityService(session)
    service._tokens = MagicMock()
    token = _auth_token()
    mutate(token)
    service._tokens.get_by_hash_any = AsyncMock(return_value=token)

    with pytest.raises(AppError) as exc_info:
        await service.verify_email("a-token")

    assert exc_info.value.code == "auth.invalid_verification_token"


@pytest.mark.asyncio
async def test_resend_verification_invalidates_previous_tokens() -> None:
    session = FakeSession()
    service = AccountSecurityService(session)
    service._tokens = MagicMock()
    service._users = MagicMock()
    user = _make_user()
    service._tokens.invalidate_outstanding = AsyncMock()
    service.send_verification_email = AsyncMock()

    await service.resend_verification(user)

    service._tokens.invalidate_outstanding.assert_awaited_once()
    # A fresh token row was staged for insert.
    assert service._tokens.add.call_count == 1
    service.send_verification_email.assert_awaited_once()
    assert session.committed is True


# ---------------------------------------------------------------------------
# Password reset
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_password_reset_unknown_email_issues_no_token() -> None:
    session = FakeSession()
    service = AccountSecurityService(session)
    service._users = MagicMock()
    service._users.get_active_by_email = AsyncMock(return_value=None)

    result = await service.request_password_reset("ghost@example.com")

    assert result is None
    assert not any(isinstance(obj, AuthToken) for obj in session.added)


@pytest.mark.asyncio
async def test_request_password_reset_known_email_issues_token_and_email() -> None:
    session = FakeSession()
    service = AccountSecurityService(session)
    service._users = MagicMock()
    user = _make_user()
    service._users.get_active_by_email = AsyncMock(return_value=user)
    service._tokens = MagicMock()
    service._tokens.invalidate_outstanding = AsyncMock()
    service.send_verification_email = MagicMock()

    # Patch the email send so no real SMTP is required.
    import app.services.account_security_service as mod

    original_send = mod.send_email
    sent: list[tuple[str, str]] = []
    mod.send_email = lambda to, subject, body: sent.append((to, subject))  # type: ignore[assignment]
    try:
        result = await service.request_password_reset("owner@example.com")
    finally:
        mod.send_email = original_send

    assert result is not None
    assert service._tokens.add.call_count == 1
    assert sent and sent[0][0] == "owner@example.com"
    assert session.committed is True


@pytest.mark.asyncio
async def test_reset_password_sets_new_hash_and_revokes_sessions() -> None:
    session = FakeSession()
    service = AccountSecurityService(session)
    service._users = MagicMock()
    service._tokens = MagicMock()
    service._refresh_tokens = MagicMock()
    user = _make_user()
    token = _auth_token(user_id=user.id, purpose=PURPOSE_PASSWORD_RESET)
    service._tokens.get_by_hash_any = AsyncMock(return_value=token)
    service._users.get_active_by_id_unscoped = AsyncMock(return_value=user)
    service._tokens.claim = AsyncMock(return_value=True)
    service._refresh_tokens.revoke_all_for_user = AsyncMock()
    user.token_version = 3

    await service.reset_password("a-valid-reset-token", "brand-new-pass")

    assert verify_password("brand-new-pass", user.password_hash)
    assert user.token_version == 4
    assert user.failed_login_attempts == 0
    assert user.locked_until is None
    service._refresh_tokens.revoke_all_for_user.assert_awaited_once()
    assert session.committed is True


@pytest.mark.asyncio
async def test_reset_password_rejects_invalid_token() -> None:
    session = FakeSession()
    service = AccountSecurityService(session)
    service._tokens = MagicMock()
    service._tokens.get_by_hash_any = AsyncMock(return_value=None)

    with pytest.raises(AppError) as exc_info:
        await service.reset_password("a-bad-token", "brand-new-pass")

    assert exc_info.value.code == "auth.invalid_reset_token"


# ---------------------------------------------------------------------------
# TOTP MFA
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mfa_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "MFA_ENABLED", False)
    session = FakeSession()
    service = MfaService(session)
    user = _make_user()

    with pytest.raises(AppError) as exc_info:
        await service.enroll(user)

    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "auth.mfa_unavailable"


@pytest.mark.asyncio
async def test_mfa_enroll_stores_pending_secret_without_enabling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "MFA_ENABLED", True)
    session = FakeSession()
    service = MfaService(session)
    user = _make_user()

    secret, otpauth_uri = await service.enroll(user)

    assert user.mfa_enabled is False
    assert user.mfa_secret_enc is not None
    assert decrypt_mfa_secret(user.mfa_secret_enc) == secret
    assert otpauth_uri.startswith("otpauth://")
    assert session.committed is True


@pytest.mark.asyncio
async def test_mfa_enroll_rejects_when_already_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "MFA_ENABLED", True)
    session = FakeSession()
    service = MfaService(session)
    user = _make_user(mfa_enabled=True)

    with pytest.raises(AppError) as exc_info:
        await service.enroll(user)

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "auth.mfa_already_enabled"


@pytest.mark.asyncio
async def test_mfa_activate_enables_and_returns_recovery_codes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "MFA_ENABLED", True)
    session = FakeSession()
    service = MfaService(session)
    service._codes = MagicMock()
    service._refresh_tokens = MagicMock()
    service._refresh_tokens.revoke_all_for_user = AsyncMock(return_value=0)
    service._codes.delete_all_for_user = AsyncMock()
    secret = generate_secret()
    user = _make_user(mfa_secret_enc=None)
    user.mfa_secret_enc = _encrypt(secret)

    code = _current_code(secret)
    recovery_codes = await service.activate(user, code)

    assert user.mfa_enabled is True
    assert len(recovery_codes) == 10
    # Recovery codes are staged as hashed rows, never stored in the clear.
    staged = [c.args[0] for c in service._codes.add.call_args_list]
    assert len(staged) == 10
    assert all(
        verify_password(raw, row.code_hash)
        for raw, row in zip(recovery_codes, staged, strict=True)
    )
    assert session.committed is True


@pytest.mark.asyncio
async def test_mfa_activate_rejects_wrong_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "MFA_ENABLED", True)
    session = FakeSession()
    service = MfaService(session)
    secret = generate_secret()
    user = _make_user(mfa_secret_enc=None)
    user.mfa_secret_enc = _encrypt(secret)

    with pytest.raises(AppError) as exc_info:
        await service.activate(user, "000000")

    assert exc_info.value.code == "auth.invalid_mfa_code"
    assert user.mfa_enabled is False


@pytest.mark.asyncio
async def test_mfa_activate_requires_enrollment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "MFA_ENABLED", True)
    session = FakeSession()
    service = MfaService(session)
    user = _make_user(mfa_secret_enc=None)

    with pytest.raises(AppError) as exc_info:
        await service.activate(user, "123456")

    assert exc_info.value.code == "auth.mfa_not_enrolled"


@pytest.mark.asyncio
async def test_mfa_disable_clears_secret_and_codes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "MFA_ENABLED", True)
    session = FakeSession()
    service = MfaService(session)
    service._codes = MagicMock()
    service._refresh_tokens = MagicMock()
    service._refresh_tokens.revoke_all_for_user = AsyncMock(return_value=0)
    service._codes.delete_all_for_user = AsyncMock()
    service._codes.list_unused = AsyncMock(return_value=[])
    secret = generate_secret()
    user = _make_user(mfa_enabled=True, mfa_secret_enc=None)
    user.mfa_secret_enc = _encrypt(secret)

    code = _current_code(secret)
    await service.disable(user, code)

    assert user.mfa_enabled is False
    assert user.mfa_secret_enc is None
    service._codes.delete_all_for_user.assert_awaited_once()
    assert session.committed is True


@pytest.mark.asyncio
async def test_mfa_disable_rejects_when_not_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "MFA_ENABLED", True)
    session = FakeSession()
    service = MfaService(session)
    user = _make_user(mfa_enabled=False)

    with pytest.raises(AppError) as exc_info:
        await service.disable(user, "123456")

    assert exc_info.value.code == "auth.mfa_not_enabled"


@pytest.mark.asyncio
async def test_mfa_challenge_token_is_not_a_usable_access_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "MFA_ENABLED", True)
    session = FakeSession()
    service = MfaService(session)
    user = _make_user()

    challenge = service.create_challenge(user)

    # The challenge carries the mfa scope; the auth guard rejects it as an
    # access token (verified at the deps layer, asserted here by claim shape).
    from app.core.security import decode_access_token

    payload = decode_access_token(challenge)
    assert payload.get("scope") == "mfa"
    assert payload.get("sub") == str(user.id)


@pytest.mark.asyncio
async def test_mfa_verify_challenge_rejects_access_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "MFA_ENABLED", True)
    session = FakeSession()
    service = MfaService(session)
    # An ordinary access token has no "scope" claim.
    access_token = create_access_token(subject=str(uuid.uuid4()))

    with pytest.raises(AppError) as exc_info:
        await service.verify_challenge(access_token, "123456")

    assert exc_info.value.code == "auth.invalid_mfa_token"


@pytest.mark.asyncio
async def test_mfa_verify_challenge_accepts_valid_totp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "MFA_ENABLED", True)
    session = FakeSession()
    service = MfaService(session)
    service._users = MagicMock()
    service._codes = MagicMock()
    service._refresh_tokens = MagicMock()
    service._refresh_tokens.revoke_all_for_user = AsyncMock(return_value=0)
    service._codes.list_unused = AsyncMock(return_value=[])
    secret = generate_secret()
    user = _make_user(mfa_enabled=True, mfa_secret_enc=None)
    user.mfa_secret_enc = _encrypt(secret)
    service._users.get_active_by_id_unscoped = AsyncMock(return_value=user)

    challenge = service.create_challenge(user)
    code = _current_code(secret)

    returned = await service.verify_challenge(challenge, code)

    assert returned is user
    assert user.mfa_failed_attempts == 0
    assert session.committed is True


@pytest.mark.asyncio
async def test_mfa_verify_challenge_consumes_recovery_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "MFA_ENABLED", True)
    session = FakeSession()
    service = MfaService(session)
    service._users = MagicMock()
    service._codes = MagicMock()
    service._refresh_tokens = MagicMock()
    service._refresh_tokens.revoke_all_for_user = AsyncMock(return_value=0)
    service._codes.mark_used = AsyncMock()
    user = _make_user(mfa_enabled=True)
    record = UserRecoveryCode(
        user_id=user.id, code_hash=hash_password("ABCD-EFGH")
    )
    record.id = uuid.uuid4()
    record.created_at = utcnow()
    service._codes.list_unused = AsyncMock(return_value=[record])
    service._users.get_active_by_id_unscoped = AsyncMock(return_value=user)

    challenge = service.create_challenge(user)
    returned = await service.verify_challenge(challenge, "abcd-efgh")

    assert returned is user
    service._codes.mark_used.assert_awaited_once()


@pytest.mark.asyncio
async def test_mfa_failed_attempts_lock_out_after_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "MFA_ENABLED", True)
    monkeypatch.setattr(settings, "MFA_MAX_ATTEMPTS", 3)
    session = FakeSession()
    service = MfaService(session)
    service._users = MagicMock()
    service._codes = MagicMock()
    service._refresh_tokens = MagicMock()
    service._refresh_tokens.revoke_all_for_user = AsyncMock(return_value=0)
    service._codes.list_unused = AsyncMock(return_value=[])
    user = _make_user(mfa_enabled=True)
    user.mfa_secret_enc = _encrypt(generate_secret())
    service._users.get_active_by_id_unscoped = AsyncMock(return_value=user)

    challenge = service.create_challenge(user)

    for _ in range(3):
        with pytest.raises(AppError):
            await service.verify_challenge(challenge, "000000")

    assert user.mfa_failed_attempts == 3
    assert user.mfa_locked_until is not None

    # A subsequent attempt is throttled with Retry-After before checking a code.
    with pytest.raises(AppError) as exc_info:
        await service.verify_challenge(challenge, _current_code_from_user(user))

    assert exc_info.value.status_code == 429
    assert exc_info.value.headers and "Retry-After" in exc_info.value.headers


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _encrypt(secret: str) -> str:
    from app.core.mfa import encrypt_mfa_secret

    return encrypt_mfa_secret(secret)


def _current_code(secret: str) -> str:
    import pyotp

    return pyotp.TOTP(secret).now()


def _current_code_from_user(user: User) -> str:
    secret = decrypt_mfa_secret(user.mfa_secret_enc)
    return _current_code(secret)


@pytest.mark.asyncio
async def test_mfa_activate_revokes_existing_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Enrolling a second factor must invalidate sessions minted without it.

    A refresh token issued before MFA enrolment would otherwise keep rotating
    for up to REFRESH_TOKEN_EXPIRE_DAYS without ever presenting the new factor.
    """
    monkeypatch.setattr(settings, "MFA_ENABLED", True)
    session = FakeSession()
    service = MfaService(session)
    service._codes = MagicMock()
    service._refresh_tokens = MagicMock()
    service._refresh_tokens.revoke_all_for_user = AsyncMock(return_value=2)
    service._codes.delete_all_for_user = AsyncMock()
    secret = generate_secret()
    user = _make_user(mfa_secret_enc=None, token_version=3)
    user.mfa_secret_enc = _encrypt(secret)

    await service.activate(user, _current_code(secret))

    assert user.mfa_enabled is True
    # Access tokens carrying the stale `tv` claim are rejected by deps.py.
    assert user.token_version == 4
    service._refresh_tokens.revoke_all_for_user.assert_awaited_once()


@pytest.mark.asyncio
async def test_mfa_disable_revokes_existing_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Removing a second factor must force every session to re-authenticate."""
    monkeypatch.setattr(settings, "MFA_ENABLED", True)
    session = FakeSession()
    service = MfaService(session)
    service._codes = MagicMock()
    service._codes.list_unused = AsyncMock(return_value=[])
    service._codes.delete_all_for_user = AsyncMock()
    service._refresh_tokens = MagicMock()
    service._refresh_tokens.revoke_all_for_user = AsyncMock(return_value=1)
    secret = generate_secret()
    user = _make_user(mfa_enabled=True, token_version=7)
    user.mfa_secret_enc = _encrypt(secret)

    await service.disable(user, _current_code(secret))

    assert user.mfa_enabled is False
    assert user.token_version == 8
    service._refresh_tokens.revoke_all_for_user.assert_awaited_once()
