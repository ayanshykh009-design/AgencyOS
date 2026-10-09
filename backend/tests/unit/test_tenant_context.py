"""Unit tests for the B-3 tenant context: GUC propagation + engine wiring.

No database required: the session/connection doubles record the statements
issued so the exact SQL contract (``set_config`` on the ``app.current_organization_id``
GUC) is asserted. Behavioral enforcement lives in
``tests/integration/test_tenant_isolation_rls.py`` (PostgreSQL-gated).
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import event

from app.api import deps
from app.core import database as db_module
from app.core.errors import AppError
from app.core.security import create_access_token
from app.core.tenant_context import (
    ORG_GUC_NAME,
    activate_org,
    deactivate_org,
    get_current_organization_id,
    set_current_organization_id,
)
from app.models.enums import UserRole
from app.models.user import User
from app.repositories.user import UserRepository

ORG_A = uuid.UUID("00000000-0000-0000-0000-0000000000a1")


class RecordingSession:
    """AsyncSession stand-in recording ``execute`` calls (no database)."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def execute(self, statement, params=None):  # noqa: ANN001
        self.calls.append((str(statement), params or {}))
        return None


class RecordingConnection:
    """Connection stand-in recording ``exec_driver_sql`` calls (no database)."""

    def __init__(self) -> None:
        self.statements: list[str] = []

    def exec_driver_sql(self, statement: str) -> None:
        self.statements.append(statement)


@pytest.fixture(autouse=True)
def _reset_tenant_context():
    set_current_organization_id(None)
    yield
    set_current_organization_id(None)


# --- ContextVar ------------------------------------------------------------


def test_contextvar_defaults_to_none():
    assert get_current_organization_id() is None


def test_contextvar_roundtrip():
    set_current_organization_id(ORG_A)
    assert get_current_organization_id() == ORG_A
    set_current_organization_id(None)
    assert get_current_organization_id() is None


# --- activate_org / deactivate_org ----------------------------------------


@pytest.mark.asyncio
async def test_activate_org_sets_contextvar_and_session_guc():
    session = RecordingSession()
    await activate_org(session, ORG_A)

    assert get_current_organization_id() == ORG_A
    assert len(session.calls) == 1
    statement, params = session.calls[0]
    assert "set_config" in statement
    assert params == {"name": ORG_GUC_NAME, "value": str(ORG_A)}


@pytest.mark.asyncio
async def test_activate_org_none_clears_contextvar_and_writes_empty_guc():
    set_current_organization_id(ORG_A)
    session = RecordingSession()
    await activate_org(session, None)

    assert get_current_organization_id() is None
    statement, params = session.calls[0]
    assert "set_config" in statement
    assert "set_config(:name, '', false)" in statement
    assert params == {"name": ORG_GUC_NAME}


@pytest.mark.asyncio
async def test_deactivate_org_delegates_to_activate_none():
    set_current_organization_id(ORG_A)
    session = RecordingSession()
    await deactivate_org(session)

    assert get_current_organization_id() is None
    assert session.calls, "deactivate_org must issue the clearing set_config"


# --- transaction-begin listener (_restore_tenant_guc) ----------------------


def test_restore_tenant_guc_writes_contextvar_value():
    set_current_organization_id(ORG_A)
    conn = RecordingConnection()
    db_module._restore_tenant_guc(conn)
    assert conn.statements == [
        f"SELECT set_config('{ORG_GUC_NAME}', '{ORG_A}', false)"
    ]


def test_restore_tenant_guc_writes_empty_string_when_unset():
    conn = RecordingConnection()
    db_module._restore_tenant_guc(conn)
    assert conn.statements == [
        f"SELECT set_config('{ORG_GUC_NAME}', '', false)"
    ]


def test_restore_tenant_guc_escapes_single_quotes(monkeypatch):
    # ContextVar values are UUIDs (which can never contain a quote), but the
    # literal is still escaped defensively — pin that behavior so a future
    # widening of the value type cannot inject SQL into the begin statement.
    class _QuoteValue:
        def __str__(self) -> str:
            return "abc'def"

    monkeypatch.setattr(db_module, "get_current_organization_id", lambda: _QuoteValue())
    conn = RecordingConnection()
    db_module._restore_tenant_guc(conn)
    assert conn.statements == [
        f"SELECT set_config('{ORG_GUC_NAME}', 'abc''def', false)"
    ]


# --- engine / factory wiring ----------------------------------------------


def test_begin_listener_attached_to_web_engine_only():
    # The web engine re-applies the tenant GUC on every transaction begin
    # (defeats pooled-connection leakage); the BYPASSRLS worker engine has no
    # tenant context to restore, so it must not carry the listener.
    assert event.contains(db_module.engine.sync_engine, "begin", db_module._restore_tenant_guc)
    assert not event.contains(
        db_module.worker_engine.sync_engine, "begin", db_module._restore_tenant_guc
    )


def test_session_factories_bind_to_their_engines():
    assert db_module.async_session_factory.kw["bind"] is db_module.engine
    assert db_module.worker_session_factory.kw["bind"] is db_module.worker_engine


# --- get_current_user (definer load + activation) --------------------------


def _make_user(*, is_active: bool = True) -> User:
    user = User(
        organization_id=ORG_A,
        email="owner@example.com",
        full_name="Owner",
        role=UserRole.OWNER,
        password_hash=None,
    )
    user.id = uuid.uuid4()
    user.is_active = is_active
    return user


def _credentials(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


@pytest.mark.asyncio
async def test_get_current_user_loads_via_definer_and_activates_org(monkeypatch):
    user = _make_user()
    unscoped = AsyncMock(return_value=user)
    monkeypatch.setattr(UserRepository, "get_active_by_id_unscoped", unscoped)
    activate = AsyncMock()
    monkeypatch.setattr(deps, "activate_org", activate)

    session = object()
    token = create_access_token(str(user.id))
    result = await deps.get_current_user(
        db=session, credentials=_credentials(token)  # type: ignore[arg-type]
    )

    assert result is user
    unscoped.assert_awaited_once_with(user.id)
    activate.assert_awaited_once_with(session, user.organization_id)


@pytest.mark.asyncio
async def test_get_current_user_rejects_missing_credentials():
    with pytest.raises(AppError) as exc_info:
        await deps.get_current_user(db=object(), credentials=None)  # type: ignore[arg-type]
    assert exc_info.value.status_code == 401
    assert exc_info.value.code == "auth.missing_token"


@pytest.mark.asyncio
async def test_get_current_user_rejects_malformed_subject(monkeypatch):
    activate = AsyncMock()
    monkeypatch.setattr(deps, "activate_org", activate)
    token = create_access_token("not-a-uuid")
    with pytest.raises(AppError) as exc_info:
        await deps.get_current_user(
            db=object(), credentials=_credentials(token)  # type: ignore[arg-type]
        )
    assert exc_info.value.status_code == 401
    assert exc_info.value.code == "auth.invalid_token"
    activate.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_current_user_rejects_invalid_signature():
    with pytest.raises(AppError) as exc_info:
        await deps.get_current_user(
            db=object(),
            credentials=_credentials("garbage.token.value"),  # type: ignore[arg-type]
        )
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_rejects_inactive_user(monkeypatch):
    user = _make_user(is_active=False)
    monkeypatch.setattr(
        UserRepository, "get_active_by_id_unscoped", AsyncMock(return_value=user)
    )
    activate = AsyncMock()
    monkeypatch.setattr(deps, "activate_org", activate)

    token = create_access_token(str(user.id))
    with pytest.raises(AppError) as exc_info:
        await deps.get_current_user(
            db=object(), credentials=_credentials(token)  # type: ignore[arg-type]
        )
    assert exc_info.value.status_code == 401
    assert exc_info.value.code == "auth.user_unavailable"
    activate.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_current_user_rejects_unknown_user(monkeypatch):
    monkeypatch.setattr(
        UserRepository, "get_active_by_id_unscoped", AsyncMock(return_value=None)
    )
    activate = AsyncMock()
    monkeypatch.setattr(deps, "activate_org", activate)

    token = create_access_token(str(uuid.uuid4()))
    with pytest.raises(AppError) as exc_info:
        await deps.get_current_user(
            db=object(), credentials=_credentials(token)  # type: ignore[arg-type]
        )
    assert exc_info.value.status_code == 401
    activate.assert_not_awaited()
