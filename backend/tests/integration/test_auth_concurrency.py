"""PostgreSQL concurrency tests for single-use authentication guarantees.

Two layers of coverage, both against a real PostgreSQL server (never mocks):

* **Service-level tests** exercise the production flows end to end:
  ``AccountSecurityService.reset_password``, ``AuthService.refresh`` (rotation
  and reuse detection), and ``MfaService.verify_challenge`` + token issuance.
  Two independent AsyncSessions race the same token/code. An
  :class:`asyncio.Barrier` synchronises the tasks *at the database mutation*
  (or, for recovery codes, immediately after the stale read) so the race is
  deterministic rather than timing-dependent. The barrier wraps the real
  repository method and delegates to it; it is not a substitute for the DB.
* **Repository-level tests** (supplemental) prove the underlying conditional
  ``UPDATE ... WHERE ... IS NULL`` claims are compare-and-swap atomic even when
  called directly.

The suite is skipped automatically when no PostgreSQL server is reachable
(local dev without a database). It is not skipped when a server is present.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

psycopg2 = pytest.importorskip("psycopg2")
from psycopg2 import sql  # noqa: E402
from sqlalchemy import text as sa_text  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool  # noqa: E402

from _pg_helpers import (  # noqa: E402
    dsn_for_database,
    ensure_compat_roles,
    enum_bootstrap_files,
)
from app.core.config import settings  # noqa: E402
from app.core.errors import AppError  # noqa: E402
from app.core.security import (  # noqa: E402
    generate_opaque_token,
    generate_refresh_token,
    hash_opaque_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.core.tenant_context import activate_org  # noqa: E402
from app.repositories.auth_token import AuthTokenRepository  # noqa: E402
from app.repositories.refresh_token import RefreshTokenRepository  # noqa: E402
from app.repositories.user import UserRepository  # noqa: E402
from app.repositories.user_recovery_code import UserRecoveryCodeRepository  # noqa: E402
from app.services.account_security_service import AccountSecurityService  # noqa: E402
from app.services.auth_service import AuthService  # noqa: E402
from app.services.base import utcnow  # noqa: E402
from app.services.mfa_service import MfaService  # noqa: E402

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "database" / "migrations"
ADMIN_URL = os.getenv(
    "TEST_POSTGRES_URL",
    settings.DATABASE_URL.replace("+asyncpg", "").rsplit("/", 1)[0] + "/postgres",
)

# A blocked task should fail the test, not hang the whole CI job forever.
BARRIER_TIMEOUT_SECONDS = 30


def _migration_files() -> list[Path]:
    return enum_bootstrap_files() + sorted(
        MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql"), key=lambda p: p.name
    )


def _database_available() -> bool:
    try:
        conn = psycopg2.connect(ADMIN_URL, connect_timeout=3)
        conn.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _database_available(), reason="PostgreSQL server not reachable"
)


def _async_url(db_name: str) -> str:
    dsn = dsn_for_database(ADMIN_URL, db_name)
    if dsn.startswith("postgresql://"):
        return dsn.replace("postgresql://", "postgresql+asyncpg://", 1)
    return dsn


@pytest.fixture()
async def pg_factory():
    """Create a disposable database with all migrations applied.

    Yields an ``async_sessionmaker`` bound to a ``NullPool`` engine so every
    concurrent task gets its own physical connection (and therefore its own
    transaction/row locks). The database is dropped afterwards.
    """
    admin = psycopg2.connect(ADMIN_URL)
    admin.autocommit = True
    ensure_compat_roles(ADMIN_URL)
    db_name = f"agencyos_conc_{uuid.uuid4().hex[:10]}"
    try:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))
    finally:
        admin.close()

    conn = psycopg2.connect(dsn_for_database(ADMIN_URL, db_name))
    engine = None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "CREATE TABLE public.schema_migrations ("
                " version text PRIMARY KEY,"
                " applied_at timestamptz NOT NULL DEFAULT now())"
            )
        conn.commit()
        for migration in _migration_files():
            with conn.cursor() as cur:
                cur.execute(migration.read_text(encoding="utf-8"))
            conn.commit()

        engine = create_async_engine(_async_url(db_name), poolclass=NullPool)
        factory = async_sessionmaker(
            bind=engine, class_=AsyncSession, expire_on_commit=False
        )
        yield factory
    finally:
        if engine is not None:
            await engine.dispose()
        conn.close()
        admin = psycopg2.connect(ADMIN_URL)
        admin.autocommit = True
        try:
            with admin.cursor() as cur:
                cur.execute(
                    sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                        sql.Identifier(db_name)
                    )
                )
        finally:
            admin.close()


async def _bind_tenant(session: AsyncSession, org_id: uuid.UUID) -> None:
    """Make a task's session behave like the production app role + tenant."""
    await session.execute(sa_text("SET ROLE agencyos_app"))
    await activate_org(session, org_id)


async def _seed_account(
    factory: async_sessionmaker[AsyncSession],
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    password: str,
    mfa_enabled: bool = False,
) -> str:
    """Insert an organization and an active owner directly, returning the email."""
    email = f"user-{user_id.hex[:12]}@example.com"
    async with factory() as session:
        await _bind_tenant(session, org_id)
        await session.execute(
            sa_text(
                "INSERT INTO organizations (id, name, slug) "
                "VALUES (:id, :name, :slug)"
            ),
            {"id": org_id, "name": "Concurrency Org", "slug": f"conc-{org_id.hex[:8]}"},
        )
        await session.execute(
            sa_text(
                "INSERT INTO users ("
                "id, organization_id, email, full_name, role, is_active, "
                "password_hash, token_version, mfa_enabled"
                ") VALUES (:id, :org, :email, :name, 'owner', true, :pw, 0, :mfa)"
            ),
            {
                "id": user_id,
                "org": org_id,
                "email": email,
                "name": "Concurrency User",
                "pw": hash_password(password),
                "mfa": mfa_enabled,
            },
        )
        await session.commit()
    return email


async def _insert_reset_token(
    factory: async_sessionmaker[AsyncSession],
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    token_hash: str,
    expires_at: datetime,
) -> None:
    async with factory() as session:
        await _bind_tenant(session, org_id)
        await session.execute(
            sa_text(
                "INSERT INTO auth_tokens (user_id, purpose, token_hash, expires_at) "
                "VALUES (:uid, 'password_reset', :hash, :expires)"
            ),
            {"uid": user_id, "hash": token_hash, "expires": expires_at},
        )
        await session.commit()


async def _insert_refresh_token(
    factory: async_sessionmaker[AsyncSession],
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    token_hash: str,
    family_id: uuid.UUID,
    expires_at: datetime,
) -> None:
    async with factory() as session:
        await _bind_tenant(session, org_id)
        await session.execute(
            sa_text(
                "INSERT INTO refresh_tokens "
                "(user_id, organization_id, token_hash, family_id, expires_at) "
                "VALUES (:uid, :org, :hash, :fam, :expires)"
            ),
            {
                "uid": user_id,
                "org": org_id,
                "hash": token_hash,
                "fam": family_id,
                "expires": expires_at,
            },
        )
        await session.commit()


async def _insert_recovery_code(
    factory: async_sessionmaker[AsyncSession],
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    raw_code: str,
) -> None:
    async with factory() as session:
        await _bind_tenant(session, org_id)
        await session.execute(
            sa_text(
                "INSERT INTO user_recovery_codes (user_id, code_hash) "
                "VALUES (:uid, :hash)"
            ),
            {"uid": user_id, "hash": hash_password(raw_code)},
        )
        await session.commit()


def _barrier_before(
    method: Callable[..., Awaitable[Any]], barrier: asyncio.Barrier
) -> Callable[..., Awaitable[Any]]:
    """Wait for both tasks, then run the real DB mutation."""

    async def wrapped(*args: Any, **kwargs: Any) -> Any:
        await asyncio.wait_for(barrier.wait(), timeout=BARRIER_TIMEOUT_SECONDS)
        return await method(*args, **kwargs)

    return wrapped


def _barrier_after(
    method: Callable[..., Awaitable[Any]], barrier: asyncio.Barrier
) -> Callable[..., Awaitable[Any]]:
    """Run the real DB read, then wait so both tasks hold the same stale read."""
    original = method

    async def wrapped(*args: Any, **kwargs: Any) -> Any:
        result = await original(*args, **kwargs)
        await asyncio.wait_for(barrier.wait(), timeout=BARRIER_TIMEOUT_SECONDS)
        return result

    return wrapped


class _CookieCapture:
    """Minimal ``Response`` stand-in that only records the refresh cookie."""

    def __init__(self) -> None:
        self.refresh_token: str | None = None

    def set_cookie(self, *, key: str, value: str, **kwargs: Any) -> None:
        if key == settings.REFRESH_COOKIE_NAME:
            self.refresh_token = value


@pytest.mark.asyncio
async def test_password_reset_atomic_claim_concurrency(pg_factory) -> None:
    """Two concurrent claim() calls on the same reset token: exactly one succeeds."""
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    raw_token = generate_opaque_token()
    await _seed_account(
        pg_factory, org_id=org_id, user_id=user_id, password="old-password"
    )
    await _insert_reset_token(
        pg_factory,
        org_id=org_id,
        user_id=user_id,
        token_hash=hash_opaque_token(raw_token),
        expires_at=utcnow() + timedelta(minutes=30),
    )

    async with pg_factory() as session:
        await _bind_tenant(session, org_id)
        record = await AuthTokenRepository(session).get_by_hash_any(
            hash_opaque_token(raw_token)
        )
        assert record is not None
        token_id = record.id

    barrier = asyncio.Barrier(2)

    async def claim_once() -> bool:
        async with pg_factory() as session:
            await _bind_tenant(session, org_id)
            repo = AuthTokenRepository(session)
            repo.claim = _barrier_before(repo.claim, barrier)  # type: ignore[method-assign]
            result = await repo.claim(token_id, "password_reset", now=utcnow())
            await session.commit()
            return result

    results = await asyncio.gather(claim_once(), claim_once())

    assert results.count(True) == 1, f"expected exactly one winner: {results}"
    assert results.count(False) == 1, f"expected exactly one loser: {results}"

    async with pg_factory() as session:
        await _bind_tenant(session, org_id)
        row = (
            await session.execute(
                sa_text("SELECT used_at FROM auth_tokens WHERE id = :id"),
                {"id": token_id},
            )
        ).one()
        assert row.used_at is not None


@pytest.mark.asyncio
async def test_refresh_token_atomic_rotation(pg_factory) -> None:
    """Two concurrent mark_replaced() calls: exactly one claims the rotation."""
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    family_id = uuid.uuid4()
    raw_refresh = generate_refresh_token()
    await _seed_account(pg_factory, org_id=org_id, user_id=user_id, password="password")
    await _insert_refresh_token(
        pg_factory,
        org_id=org_id,
        user_id=user_id,
        token_hash=hash_refresh_token(raw_refresh),
        family_id=family_id,
        expires_at=utcnow() + timedelta(days=30),
    )

    async with pg_factory() as session:
        await _bind_tenant(session, org_id)
        record = await RefreshTokenRepository(session).get_any(
            hash_refresh_token(raw_refresh)
        )
        assert record is not None
        token_id = record.id

    successor_a = uuid.uuid4()
    successor_b = uuid.uuid4()
    barrier = asyncio.Barrier(2)

    async def rotate_once(successor_id: uuid.UUID):
        async with pg_factory() as session:
            await _bind_tenant(session, org_id)
            repo = RefreshTokenRepository(session)
            repo.mark_replaced = _barrier_before(  # type: ignore[method-assign]
                repo.mark_replaced, barrier
            )
            claimed = await repo.mark_replaced(token_id, successor_id, now=utcnow())
            await session.commit()
            return successor_id, claimed

    results = await asyncio.gather(
        rotate_once(successor_a), rotate_once(successor_b)
    )
    winners = [successor for successor, claimed in results if claimed]
    losers = [successor for successor, claimed in results if not claimed]
    assert len(winners) == 1, f"expected exactly one winner: {results}"
    assert len(losers) == 1, f"expected exactly one loser: {results}"

    async with pg_factory() as session:
        await _bind_tenant(session, org_id)
        row = (
            await session.execute(
                sa_text(
                    "SELECT revoked_at, replaced_by FROM refresh_tokens WHERE id = :id"
                ),
                {"id": token_id},
            )
        ).one()
        assert row.revoked_at is not None
        assert row.replaced_by == winners[0]


@pytest.mark.asyncio
async def test_mfa_recovery_code_concurrent_consumption(pg_factory) -> None:
    """Two concurrent mark_used() calls on one recovery code: one consumes it."""
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    raw_code = "ABCD-EFGH-JKLM"
    await _seed_account(
        pg_factory,
        org_id=org_id,
        user_id=user_id,
        password="password",
        mfa_enabled=True,
    )
    await _insert_recovery_code(
        pg_factory, org_id=org_id, user_id=user_id, raw_code=raw_code
    )

    async with pg_factory() as session:
        await _bind_tenant(session, org_id)
        record = (
            await session.execute(
                sa_text(
                    "SELECT id FROM user_recovery_codes WHERE user_id = :uid "
                    "AND used_at IS NULL"
                ),
                {"uid": user_id},
            )
        ).one()
        code_id = record.id

    barrier = asyncio.Barrier(2)

    async def consume_once() -> bool:
        async with pg_factory() as session:
            await _bind_tenant(session, org_id)
            repo = UserRecoveryCodeRepository(session)
            repo.mark_used = _barrier_before(  # type: ignore[method-assign]
                repo.mark_used, barrier
            )
            result = await repo.mark_used(code_id, now=utcnow())
            await session.commit()
            return result

    results = await asyncio.gather(consume_once(), consume_once())

    assert results.count(True) == 1, f"expected exactly one consumer: {results}"
    assert results.count(False) == 1, f"expected exactly one rejected: {results}"

    async with pg_factory() as session:
        await _bind_tenant(session, org_id)
        row = (
            await session.execute(
                sa_text("SELECT used_at FROM user_recovery_codes WHERE id = :id"),
                {"id": code_id},
            )
        ).one()
        assert row.used_at is not None


@pytest.mark.asyncio
async def test_service_password_reset_single_winner(pg_factory) -> None:
    """Concurrent ``reset_password`` calls: only the winner may mutate the account.

    The token claim is the serialization point. The loser must fail *before*
    changing the password hash, bumping ``token_version``, or revoking the
    user's sessions. Each task uses a different new password so the final hash
    proves which request actually mutated the account.
    """
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    raw_token = generate_opaque_token()
    family_id = uuid.uuid4()
    await _seed_account(pg_factory, org_id=org_id, user_id=user_id, password="old-pw")
    await _insert_reset_token(
        pg_factory,
        org_id=org_id,
        user_id=user_id,
        token_hash=hash_opaque_token(raw_token),
        expires_at=utcnow() + timedelta(minutes=30),
    )
    await _insert_refresh_token(
        pg_factory,
        org_id=org_id,
        user_id=user_id,
        token_hash=hash_refresh_token(generate_refresh_token()),
        family_id=family_id,
        expires_at=utcnow() + timedelta(days=30),
    )

    barrier = asyncio.Barrier(2)

    async def reset_once(label: str, new_password: str):
        async with pg_factory() as session:
            await _bind_tenant(session, org_id)
            service = AccountSecurityService(session)
            service._tokens.claim = _barrier_before(  # type: ignore[method-assign]
                service._tokens.claim, barrier
            )
            try:
                await service.reset_password(raw_token, new_password)
                return label, new_password, None
            except AppError as exc:
                return label, new_password, exc

    outcomes = await asyncio.gather(
        reset_once("a", "winner-candidate-a"),
        reset_once("b", "winner-candidate-b"),
    )
    assert all(isinstance(outcome, tuple) for outcome in outcomes), outcomes

    successes = [outcome for outcome in outcomes if outcome[2] is None]
    failures = [outcome for outcome in outcomes if outcome[2] is not None]
    assert len(successes) == 1, f"expected one success: {outcomes}"
    assert len(failures) == 1, f"expected one failure: {outcomes}"
    loser_error = failures[0][2]
    assert isinstance(loser_error, AppError)
    assert loser_error.code == "auth.invalid_reset_token"

    winner_password = successes[0][1]
    loser_password = failures[0][1]

    async with pg_factory() as session:
        await _bind_tenant(session, org_id)
        user_row = (
            await session.execute(
                sa_text(
                    "SELECT password_hash, token_version, failed_login_attempts, "
                    "locked_until FROM users WHERE id = :uid"
                ),
                {"uid": user_id},
            )
        ).one()
        token_row = (
            await session.execute(
                sa_text("SELECT used_at FROM auth_tokens WHERE token_hash = :hash"),
                {"hash": hash_opaque_token(raw_token)},
            )
        ).one()
        refresh_row = (
            await session.execute(
                sa_text(
                    "SELECT revoked_at FROM refresh_tokens WHERE user_id = :uid"
                ),
                {"uid": user_id},
            )
        ).one()

    assert verify_password(winner_password, user_row.password_hash)
    assert not verify_password(loser_password, user_row.password_hash)
    assert user_row.token_version == 1
    assert user_row.failed_login_attempts == 0
    assert user_row.locked_until is None
    assert token_row.used_at is not None
    assert refresh_row.revoked_at is not None


@pytest.mark.asyncio
async def test_service_refresh_rotation_revokes_whole_family(pg_factory) -> None:
    """Concurrent ``AuthService.refresh`` calls trigger the real reuse policy.

    Exactly one request returns a token pair. The losing request detects reuse
    and revokes the whole family (including the winner's newly minted
    successor) plus bumps ``token_version``, so no unintended active successor
    survives. The winner's refresh token is captured from the cookie to prove
    the old row links to it via ``replaced_by``.
    """
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    family_id = uuid.uuid4()
    raw_refresh = generate_refresh_token()
    await _seed_account(pg_factory, org_id=org_id, user_id=user_id, password="password")
    await _insert_refresh_token(
        pg_factory,
        org_id=org_id,
        user_id=user_id,
        token_hash=hash_refresh_token(raw_refresh),
        family_id=family_id,
        expires_at=utcnow() + timedelta(days=30),
    )

    barrier = asyncio.Barrier(2)

    async def refresh_once(label: str):
        async with pg_factory() as session:
            await _bind_tenant(session, org_id)
            service = AuthService(session)
            service._tokens.mark_replaced = _barrier_before(  # type: ignore[method-assign]
                service._tokens.mark_replaced, barrier
            )
            capture = _CookieCapture()
            try:
                response = await service.refresh(raw_refresh, response=capture)
                return label, response, capture.refresh_token, None
            except AppError as exc:
                return label, None, None, exc

    outcomes = await asyncio.gather(
        refresh_once("a"), refresh_once("b")
    )
    assert all(isinstance(outcome, tuple) for outcome in outcomes), outcomes

    successes = [outcome for outcome in outcomes if outcome[3] is None]
    failures = [outcome for outcome in outcomes if outcome[3] is not None]
    assert len(successes) == 1, f"expected one success: {outcomes}"
    assert len(failures) == 1, f"expected one failure: {outcomes}"
    loser_error = failures[0][3]
    assert isinstance(loser_error, AppError)
    assert loser_error.code == "auth.refresh_token_reuse"

    winner_refresh = successes[0][2]
    assert winner_refresh is not None

    async with pg_factory() as session:
        await _bind_tenant(session, org_id)
        winner_row = (
            await session.execute(
                sa_text("SELECT id FROM refresh_tokens WHERE token_hash = :hash"),
                {"hash": hash_refresh_token(winner_refresh)},
            )
        ).one()
        old_row = (
            await session.execute(
                sa_text(
                    "SELECT revoked_at, replaced_by FROM refresh_tokens "
                    "WHERE token_hash = :hash"
                ),
                {"hash": hash_refresh_token(raw_refresh)},
            )
        ).one()
        family_rows = (
            await session.execute(
                sa_text(
                    "SELECT id, revoked_at FROM refresh_tokens WHERE family_id = :fam"
                ),
                {"fam": family_id},
            )
        ).all()
        user_row = (
            await session.execute(
                sa_text("SELECT token_version FROM users WHERE id = :uid"),
                {"uid": user_id},
            )
        ).one()

    assert old_row.revoked_at is not None
    assert old_row.replaced_by == winner_row.id
    assert len(family_rows) == 3, family_rows
    assert all(row.revoked_at is not None for row in family_rows)
    assert user_row.token_version == 1


@pytest.mark.asyncio
async def test_service_mfa_recovery_code_single_authentication(
    pg_factory, monkeypatch
) -> None:
    """Concurrent MFA verifications with one recovery code: one authentication.

    ``list_unused`` is wrapped to wait until both tasks have executed the stale
    read, so both definitely observe the unused code before either can claim
    it. Only the winner may mint a session; exactly one refresh token and one
    consumed recovery code must remain.
    """
    monkeypatch.setattr(settings, "MFA_ENABLED", True)
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    raw_code = "ZZZZ-YYYY-XXXX"
    await _seed_account(
        pg_factory,
        org_id=org_id,
        user_id=user_id,
        password="password",
        mfa_enabled=True,
    )
    await _insert_recovery_code(
        pg_factory, org_id=org_id, user_id=user_id, raw_code=raw_code
    )

    async with pg_factory() as session:
        await _bind_tenant(session, org_id)
        user = await UserRepository(session).get_active_by_id_unscoped(user_id)
        assert user is not None
        challenge = MfaService(session).create_challenge(user)

    barrier = asyncio.Barrier(2)

    async def verify_once(label: str):
        async with pg_factory() as session:
            await _bind_tenant(session, org_id)
            service = MfaService(session)
            service._codes.list_unused = _barrier_after(  # type: ignore[method-assign]
                service._codes.list_unused, barrier
            )
            try:
                user = await service.verify_challenge(challenge, raw_code)
            except AppError as exc:
                return label, None, exc
            response = await AuthService(session).session_for_user(user)
            return label, response, None

    outcomes = await asyncio.gather(
        verify_once("a"), verify_once("b")
    )
    assert all(isinstance(outcome, tuple) for outcome in outcomes), outcomes

    successes = [outcome for outcome in outcomes if outcome[2] is None]
    failures = [outcome for outcome in outcomes if outcome[2] is not None]
    assert len(successes) == 1, f"expected one authentication: {outcomes}"
    assert len(failures) == 1, f"expected one rejection: {outcomes}"
    loser_error = failures[0][2]
    assert isinstance(loser_error, AppError)
    assert loser_error.code == "auth.invalid_mfa_code"
    assert successes[0][1].user.id == user_id

    async with pg_factory() as session:
        await _bind_tenant(session, org_id)
        code_row = (
            await session.execute(
                sa_text(
                    "SELECT used_at FROM user_recovery_codes WHERE user_id = :uid"
                ),
                {"uid": user_id},
            )
        ).one()
        used_count = (
            await session.execute(
                sa_text(
                    "SELECT count(*) FROM user_recovery_codes "
                    "WHERE user_id = :uid AND used_at IS NOT NULL"
                ),
                {"uid": user_id},
            )
        ).scalar_one()
        session_count = (
            await session.execute(
                sa_text("SELECT count(*) FROM refresh_tokens WHERE user_id = :uid"),
                {"uid": user_id},
            )
        ).scalar_one()

    assert code_row.used_at is not None
    assert used_count == 1
    assert session_count == 1
