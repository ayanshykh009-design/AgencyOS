"""Integration tests for the Founder AI Assistant (M8) against a real PostgreSQL.

These exercise the new tables, repositories, approval-gated action service, and
chat persistence end-to-end. They are skipped automatically when no PostgreSQL
server is reachable (local dev), and run in CI against the ``postgres`` service.
"""
from __future__ import annotations

import os
import uuid
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest

pytest.importorskip("psycopg2")
import psycopg2  # noqa: E402
from psycopg2 import sql  # noqa: E402
from sqlalchemy import select as sa_select  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool  # noqa: E402

from _pg_helpers import dsn_for_database, ensure_compat_roles  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.errors import AppError  # noqa: E402
from app.models.enums import FounderProposalStatus, TaskStatus  # noqa: E402
from app.models.founder_action_proposal import FounderActionProposal  # noqa: E402
from app.models.task import Task  # noqa: E402
from app.models.user import User  # noqa: E402
from app.schemas.auth import RegisterRequest  # noqa: E402
from app.services.approval_service import ApprovalService  # noqa: E402
from app.services.auth_service import AuthService  # noqa: E402
from app.services.base import utcnow  # noqa: E402
from app.services.founder_action_service import FounderActionService  # noqa: E402
from app.services.founder_chat_service import FounderChatService  # noqa: E402

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "database" / "migrations"
ADMIN_URL = os.getenv(
    "TEST_POSTGRES_URL",
    settings.DATABASE_URL.replace("+asyncpg", "").rsplit("/", 1)[0] + "/postgres",
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


def _migration_files() -> list[Path]:
    return sorted(
        Path(MIGRATIONS_DIR).glob("[0-9][0-9][0-9][0-9]_*.sql"),
        key=lambda p: p.name,
    )


def _async_url_for(db_name: str) -> str:
    base = os.getenv("TEST_POSTGRES_URL", "").replace("+asyncpg", "") or settings.DATABASE_URL
    parts = urlsplit(base.replace("+asyncpg", ""))
    return urlunsplit(("postgresql+asyncpg", parts.netloc, f"/{db_name}", "", ""))


@pytest.fixture()
async def db():
    """Create a disposable database with all migrations applied, yield an
    async session factory, then drop it."""
    admin = psycopg2.connect(ADMIN_URL)
    admin.autocommit = True
    ensure_compat_roles(ADMIN_URL)
    db_name = f"agencyos_founder_{uuid.uuid4().hex[:8]}"
    with admin.cursor() as cur:
        cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))

    conn = None
    engine = None
    try:
        conn = psycopg2.connect(dsn_for_database(ADMIN_URL, db_name))
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

        engine = create_async_engine(_async_url_for(db_name), poolclass=NullPool)
        factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
        yield factory
    finally:
        if engine is not None:
            await engine.dispose()
        if conn is not None:
            conn.close()
        with admin.cursor() as cur:
            cur.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(db_name))
            )
        admin.close()


async def _register(db) -> tuple[uuid.UUID, uuid.UUID]:
    """Register an org; return (organization_id, user_id)."""
    async with db() as session:
        result = await AuthService(session).register(
            RegisterRequest(
                email="founder@example.com",
                password="S3cure!pass",
                full_name="Founder",
                organization_name="Founder Co",
                organization_slug=f"founder-{uuid.uuid4().hex[:8]}",
            )
        )
        user = await session.get(User, result.user.id)
        assert user is not None
        return user.organization_id, user.id


async def test_chat_persists_messages_without_llm(db) -> None:
    org_id, user_id = await _register(db)
    async with db() as session:
        chat = FounderChatService(session)
        user = await session.get(User, user_id)
        out = await chat.send_message(
            org_id, user, conversation_id=None, message="What is our pipeline health?"
        )
        # Without an LLM configured the executor fails open but the turn is
        # persisted: a conversation + user + assistant messages exist.
        assert out["conversation_id"]
        assert out["ok"] is False

        conversations = await chat.list_conversations(org_id)
        assert len(conversations) == 1
        assert conversations[0].title is not None

        loaded = await chat.get_conversation(org_id, uuid.UUID(out["conversation_id"]))
        assert len(loaded["messages"]) == 2
        senders = {m["sender"] for m in loaded["messages"]}
        assert senders == {"user", "assistant"}


async def test_propose_and_approve_creates_task(db) -> None:
    org_id, user_id = await _register(db)
    async with db() as session:
        svc = FounderActionService(session)
        proposal = await svc.propose(
            organization_id=org_id,
            actor_user_id=user_id,
            conversation_id=None,
            action_type="create_task",
            title="Create task: Follow up",
            payload={"title": "Follow up", "priority": "high"},
            justification="quarterly",
        )
        assert proposal.proposal_status == FounderProposalStatus.PROPOSED
        assert proposal.approval_request_id is not None

        decided = await svc.decide_proposal(
            org_id, user_id, proposal.id, approve=True
        )
        assert decided.proposal_status == FounderProposalStatus.SUCCEEDED

        created = (
            await session.execute(
                sa_select(Task).where(Task.organization_id == org_id)
            )
        ).scalars().all()
        assert len(created) == 1
        assert created[0].status == TaskStatus.TODO
        assert created[0].title == "Follow up"


async def test_propose_deny_marks_denied(db) -> None:
    org_id, user_id = await _register(db)
    async with db() as session:
        svc = FounderActionService(session)
        proposal = await svc.propose(
            organization_id=org_id,
            actor_user_id=user_id,
            conversation_id=None,
            action_type="create_task",
            title="Create task: X",
            payload={"title": "X"},
        )
        decided = await svc.decide_proposal(org_id, user_id, proposal.id, approve=False)
        assert decided.proposal_status == FounderProposalStatus.DENIED

        # No task should be created on denial.
        created = (
            await session.execute(
                sa_select(Task).where(Task.organization_id == org_id)
            )
        ).scalars().all()
        assert created == []


async def test_expire_due_all_sweeps_expired(db) -> None:
    org_id, user_id = await _register(db)
    async with db() as session:
        # Insert a proposal directly with an already-passed expiry.
        proposal = FounderActionProposal(
            organization_id=org_id,
            conversation_id=None,
            approval_request_id=None,
            proposal_status=FounderProposalStatus.PROPOSED,
            action_type="create_task",
            title="Stale proposal",
            payload={},
            expires_at=utcnow() - timedelta(days=1),
            actor_user_id=user_id,
        )
        session.add(proposal)
        await session.flush()

        svc = FounderActionService(session)
        handled = await svc.expire_due_all(now=utcnow())
        assert handled >= 1

        refreshed = await session.get(FounderActionProposal, proposal.id)
        assert refreshed.proposal_status == FounderProposalStatus.EXPIRED


async def test_expired_proposal_rejected_at_synchronous_gate(db) -> None:
    """A PROPOSED proposal past its ``expires_at`` must be un-approvable even
    when the background expiry sweep is not running (regression for the
    time-box bypass where an expired proposal could still be approved/executed).
    """
    org_id, user_id = await _register(db)
    async with db() as session:
        svc = FounderActionService(session)
        proposal = await svc.propose(
            organization_id=org_id,
            actor_user_id=user_id,
            conversation_id=None,
            action_type="create_task",
            title="Late approval",
            payload={"title": "Late"},
        )
        # Backdate the proposal and its linked approval request.
        proposal.expires_at = utcnow() - timedelta(hours=1)
        from app.repositories.approval_request import ApprovalRequestRepository

        approval = await ApprovalRequestRepository(session).get(
            org_id, proposal.approval_request_id
        )
        approval.expires_at = utcnow() - timedelta(hours=1)
        await session.commit()

        with pytest.raises(AppError) as exc:
            await svc.decide_proposal(org_id, user_id, proposal.id, approve=True)
        assert exc.value.status_code == 409

        refreshed = await session.get(FounderActionProposal, proposal.id)
        assert refreshed.proposal_status == FounderProposalStatus.EXPIRED
        # No task should have been created by an expired proposal.
        created = (
            await session.execute(
                sa_select(Task).where(Task.organization_id == org_id)
            )
        ).scalars().all()
        assert created == []


async def test_expired_approval_request_rejected_at_synchronous_gate(db) -> None:
    """``ApprovalService.decide`` must reject a PENDING request past its
    ``expires_at`` (not only the background sweep)."""
    org_id, user_id = await _register(db)
    async with db() as session:
        user = await session.get(User, user_id)
        approvals = ApprovalService(session)
        request = await approvals.create_request(
            organization_id=org_id,
            requested_by_user_id=user_id,
            actor=user,
            workflow_id=None,
            workflow_execution_id=None,
            approver_user_id=user_id,
            title="expired request",
            details="{}",
            expires_at=utcnow() - timedelta(hours=1),
        )
        with pytest.raises(AppError) as exc:
            await approvals.decide(
                org_id,
                actor=user,
                request_id=request.id,
                approve=True,
                decided_by_user_id=user_id,
            )
        assert exc.value.status_code == 409
