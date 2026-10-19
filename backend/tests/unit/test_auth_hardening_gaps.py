"""Regression tests for the gaps closed by the unified auth-security pass.

Three controls are covered here:

1. ``app.core.db_roles.evaluate_role`` — the fail-closed policy that stops a
   production deployment from connecting as the cluster owner/superuser, which
   would bypass every RLS policy while the behavioural suite stayed green.
2. ``app.api.deps.get_current_user`` — email verification enforced on *every*
   authenticated request, not only at login.
3. ``AuthService.refresh`` — rotation cannot be used to outlive the
   email-verification gate.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api import deps
from app.core.db_roles import APP_ROLE, WORKER_ROLE, evaluate_role
from app.core.errors import AppError
from app.models.enums import UserRole
from app.models.user import User
from app.services.auth_service import AuthService
from app.services.base import utcnow

ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


# ---------------------------------------------------------------------------
# 1. Runtime database role policy
# ---------------------------------------------------------------------------


def _evaluate(**overrides: object) -> str | None:
    base: dict[str, object] = {
        "rolname": "agencyos_api",
        "rolsuper": False,
        "app_member": True,
        "worker_member": False,
        "dsn_label": "DATABASE_URL",
        "require_group": APP_ROLE,
    }
    base.update(overrides)
    return evaluate_role(**base)  # type: ignore[arg-type]


def test_accepts_restricted_app_role() -> None:
    assert _evaluate() is None


def test_rejects_superuser_dsn() -> None:
    """The shipped docker-compose default connects as the cluster owner."""
    err = _evaluate(rolname="agencyos", rolsuper=True, app_member=False)
    assert err is not None
    assert "SUPERUSER" in err
    assert "DATABASE_URL" in err


def test_rejects_owner_role_that_is_not_app_member() -> None:
    """A non-superuser table owner still bypasses RLS (no FORCE RLS in 0033)."""
    err = _evaluate(rolname="agencyos", app_member=False)
    assert err is not None
    assert APP_ROLE in err
    assert "GRANT" in err


def test_rejects_unresolvable_role() -> None:
    assert _evaluate(rolname=None) is not None


def test_worker_dsn_requires_worker_membership() -> None:
    err = _evaluate(
        rolname="agencyos_workers",
        app_member=False,
        worker_member=False,
        dsn_label="WORKER_DATABASE_URL",
        require_group=WORKER_ROLE,
    )
    assert err is not None
    assert WORKER_ROLE in err


def test_worker_dsn_accepts_bypassrls_member() -> None:
    """Workers are BYPASSRLS by design; only group membership is required."""
    assert (
        _evaluate(
            rolname="agencyos_workers",
            app_member=False,
            worker_member=True,
            dsn_label="WORKER_DATABASE_URL",
            require_group=WORKER_ROLE,
        )
        is None
    )


def test_worker_superuser_still_rejected() -> None:
    err = _evaluate(
        rolname="agencyos",
        rolsuper=True,
        worker_member=True,
        dsn_label="WORKER_DATABASE_URL",
        require_group=WORKER_ROLE,
    )
    assert err is not None
    assert "SUPERUSER" in err


async def test_verify_roles_is_noop_outside_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Developer/CI owner connections must keep working unchanged."""
    from app.core.config import settings
    from app.core.db_roles import verify_runtime_database_roles

    monkeypatch.setattr(settings, "APP_ENV", "development")
    assert await verify_runtime_database_roles() is None


# ---------------------------------------------------------------------------
# 2/3. Email verification enforced beyond the login path
# ---------------------------------------------------------------------------


def _make_user(**overrides: object) -> User:
    user = User(
        organization_id=ORG_ID,
        email="owner@example.com",
        full_name="Owner",
        role=UserRole.OWNER,
        password_hash="x",
    )
    user.id = uuid.uuid4()
    user.created_at = utcnow()
    user.updated_at = utcnow()
    user.is_active = True
    user.token_version = 0
    user.email_verified_at = None
    user.email_verification_required = False
    for key, value in overrides.items():
        setattr(user, key, value)
    return user


def _credentials() -> object:
    cred = MagicMock()
    cred.credentials = "token"
    return cred


async def test_get_current_user_rejects_unverified_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """register() mints tokens immediately, so the gate must live in deps too."""
    user = _make_user(email_verification_required=True, email_verified_at=None)
    monkeypatch.setattr(deps, "require_valid_token", lambda _t: {"sub": str(user.id), "tv": 0})
    repo = MagicMock()
    repo.get_active_by_id_unscoped = AsyncMock(return_value=user)
    monkeypatch.setattr(deps, "UserRepository", lambda _db: repo)
    monkeypatch.setattr(deps, "activate_org", AsyncMock())

    with pytest.raises(AppError) as exc_info:
        await deps.get_current_user(db=MagicMock(), credentials=_credentials())  # type: ignore[arg-type]

    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "auth.email_verification_required"


async def test_get_current_user_allows_verified_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _make_user(email_verification_required=True, email_verified_at=utcnow())
    monkeypatch.setattr(deps, "require_valid_token", lambda _t: {"sub": str(user.id), "tv": 0})
    repo = MagicMock()
    repo.get_active_by_id_unscoped = AsyncMock(return_value=user)
    monkeypatch.setattr(deps, "UserRepository", lambda _db: repo)
    monkeypatch.setattr(deps, "activate_org", AsyncMock())

    resolved = await deps.get_current_user(db=MagicMock(), credentials=_credentials())  # type: ignore[arg-type]
    assert resolved is user


async def test_get_current_user_allows_grandfathered_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Existing users are grandfathered: the flag is False, so no gate applies."""
    user = _make_user(email_verification_required=False, email_verified_at=None)
    monkeypatch.setattr(deps, "require_valid_token", lambda _t: {"sub": str(user.id), "tv": 0})
    repo = MagicMock()
    repo.get_active_by_id_unscoped = AsyncMock(return_value=user)
    monkeypatch.setattr(deps, "UserRepository", lambda _db: repo)
    monkeypatch.setattr(deps, "activate_org", AsyncMock())

    resolved = await deps.get_current_user(db=MagicMock(), credentials=_credentials())  # type: ignore[arg-type]
    assert resolved is user


async def test_refresh_rejects_unverified_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rotation must not become a way around the verification gate."""
    user = _make_user(email_verification_required=True, email_verified_at=None)
    record = MagicMock()
    record.revoked_at = None
    record.expires_at = utcnow() + timedelta(days=1)
    record.organization_id = ORG_ID
    record.user_id = user.id
    record.id = uuid.uuid4()
    record.family_id = uuid.uuid4()

    session = MagicMock()
    service = AuthService(session)
    service._tokens = MagicMock()
    service._tokens.get_any = AsyncMock(return_value=record)
    service._users = MagicMock()
    service._users.get = AsyncMock(return_value=user)
    service._issue_tokens = AsyncMock()
    monkeypatch.setattr("app.services.auth_service.activate_org", AsyncMock(), raising=False)
    monkeypatch.setattr(
        "app.services.auth_service.hash_refresh_token", lambda _t: "h", raising=False
    )

    with pytest.raises(AppError) as exc_info:
        await service.refresh("raw-token")

    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "auth.email_verification_required"
    service._issue_tokens.assert_not_awaited()
