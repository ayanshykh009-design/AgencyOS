"""Service-layer unit tests.

The service layer owns business rules and the transaction boundary. These
tests swap the concrete repositories for lightweight fakes so the rules are
verified without a database. Repository SQL is covered by the integration
suite (which runs against a real PostgreSQL server in CI).
"""
import uuid
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.errors import AppError
from app.core.security import hash_password, verify_password
from app.models.conversation import Conversation
from app.models.enums import (
    ConversationSender,
    ImportStatus,
    LeadStatus,
    OutreachChannel,
    UserRole,
)
from app.models.lead import Lead
from app.models.organization import Organization
from app.models.provider_usage import ProviderUsage
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest
from app.services.auth_service import AuthService
from app.services.base import utcnow
from app.services.conversation_service import ConversationService
from app.services.import_service import ImportService
from app.services.lead_service import LeadService
from app.services.provider_usage_service import ProviderUsageService

ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
LEAD_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")


class FakeSession:
    """Minimal async session: records adds; flush/commit/rollback are no-ops."""

    def __init__(self, *, fail_on_flush: int = 0) -> None:
        self.added: list[object] = []
        self.committed = False
        self.rolled_back = False
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
        self.rolled_back = True

    async def refresh(self, instance: object) -> None:
        # No-op: the fake has no database to reload attributes from.
        return None

    async def execute(self, *args: object, **kwargs: object) -> None:
        # Accepts statements such as tenant GUC set_config() without a DB.
        return None


def _make_user(**overrides: object) -> User:
    user = User(
        organization_id=ORG_ID,
        email="owner@example.com",
        full_name="Owner",
        role=UserRole.OWNER,
        password_hash=None,
    )
    user.id = uuid.uuid4()
    user.created_at = utcnow()
    user.updated_at = utcnow()
    user.is_active = True
    for key, value in overrides.items():
        setattr(user, key, value)
    return user


def _timeful_user(**kwargs: object) -> User:
    """Replace ``auth_service.User`` so constructed users validate as UserRead."""
    user = User(**kwargs)
    user.id = uuid.uuid4()
    user.created_at = utcnow()
    user.updated_at = utcnow()
    user.is_active = kwargs.get("is_active", True)
    return user


def _timeful_org(**kwargs: object) -> Organization:
    """Replace ``auth_service.Organization`` so transient orgs carry an id."""
    org = Organization(**kwargs)
    org.id = uuid.uuid4()
    return org


def _register_payload(**overrides: object) -> RegisterRequest:
    base: dict[str, object] = {
        "email": "owner@example.com",
        "password": "S3cure!pass",
        "full_name": "Owner",
        "organization_name": "Acme Agency",
        "organization_slug": "acme",
    }
    base.update(overrides)
    return RegisterRequest(**base)


# ---------------------------------------------------------------------------
# AuthService
# ---------------------------------------------------------------------------

# auth_service constructs User/Organization instances (server defaults fill
# timestamps on INSERT); patch the constructors so transient instances are
# UserRead-valid and carry ids.
AUTH_USER_PATCH = "app.services.auth_service.User"
AUTH_ORG_PATCH = "app.services.auth_service.Organization"


def _patch_auth_models(monkeypatch) -> None:
    monkeypatch.setattr(AUTH_USER_PATCH, _timeful_user)
    monkeypatch.setattr(AUTH_ORG_PATCH, _timeful_org)


@pytest.mark.asyncio
async def test_register_creates_org_owner_and_tokens(monkeypatch) -> None:
    _patch_auth_models(monkeypatch)
    session = FakeSession()
    service = AuthService(session)
    service._orgs = MagicMock()
    service._users = MagicMock()
    service._tokens = MagicMock()
    service._orgs.ensure_slug_available = AsyncMock()
    service._orgs.add = MagicMock(side_effect=session.add)
    service._users.add = MagicMock(side_effect=session.add)
    service._tokens.add = MagicMock(side_effect=session.add)

    result = await service.register(_register_payload())

    assert result.access_token
    # refresh token is now delivered via the HttpOnly cookie, not the JSON body
    assert result.access_token
    assert result.user.email == "owner@example.com"
    assert result.user.role is UserRole.OWNER
    assert session.committed is True
    # Org + owner user were added (in order) before tokens.
    added = session.added
    assert any(isinstance(obj, Organization) for obj in added)
    assert any(isinstance(obj, User) for obj in added)


@pytest.mark.asyncio
async def test_register_normalizes_email(monkeypatch) -> None:
    _patch_auth_models(monkeypatch)
    session = FakeSession()
    service = AuthService(session)
    service._orgs = MagicMock()
    service._users = MagicMock()
    service._tokens = MagicMock()
    service._orgs.ensure_slug_available = AsyncMock()
    service._orgs.add = MagicMock(side_effect=session.add)
    service._users.add = MagicMock(side_effect=session.add)
    service._tokens.add = MagicMock(side_effect=session.add)

    await service.register(_register_payload(email="Owner@Example.COM"))

    created_user = next(obj for obj in session.added if isinstance(obj, User))
    assert created_user.email == "owner@example.com"


@pytest.mark.asyncio
async def test_register_raises_409_when_email_taken(monkeypatch) -> None:
    _patch_auth_models(monkeypatch)
    session = FakeSession(fail_on_flush=2)
    service = AuthService(session)
    service._orgs = MagicMock()
    service._users = MagicMock()
    service._tokens = MagicMock()
    service._orgs.ensure_slug_available = AsyncMock()
    service._orgs.add = MagicMock(side_effect=session.add)
    service._users.add = MagicMock(side_effect=session.add)
    service._tokens.add = MagicMock(side_effect=session.add)
    service._users.get_by_email = AsyncMock(return_value=_make_user())
    service._orgs.get_by_slug = AsyncMock(return_value=None)

    with pytest.raises(AppError) as exc_info:
        await service.register(_register_payload())

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "user.email_taken"


@pytest.mark.asyncio
async def test_register_raises_409_when_slug_taken(monkeypatch) -> None:
    _patch_auth_models(monkeypatch)
    session = FakeSession(fail_on_flush=2)
    service = AuthService(session)
    service._orgs = MagicMock()
    service._users = MagicMock()
    service._tokens = MagicMock()
    service._orgs.ensure_slug_available = AsyncMock()
    service._orgs.add = MagicMock(side_effect=session.add)
    service._users.add = MagicMock(side_effect=session.add)
    service._tokens.add = MagicMock(side_effect=session.add)
    service._users.get_by_email = AsyncMock(return_value=None)
    service._orgs.get_by_slug = AsyncMock(return_value=Organization(name="x", slug="acme"))

    with pytest.raises(AppError) as exc_info:
        await service.register(_register_payload())

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "organization.slug_taken"


@pytest.mark.asyncio
async def test_login_success_issues_tokens_and_stamps_last_login() -> None:
    session = FakeSession()
    service = AuthService(session)
    service._orgs = MagicMock()
    service._users = MagicMock()
    service._tokens = MagicMock()
    user = _make_user(password_hash=hash_password("S3cure!pass"))
    service._users.get_active_by_email = AsyncMock(return_value=user)
    service._tokens.add = MagicMock()

    result = await service.login(
        LoginRequest(email="owner@example.com", password="S3cure!pass")
    )

    assert result.access_token
    assert user.last_login_at is not None
    assert session.committed is True


@pytest.mark.asyncio
async def test_login_rejects_wrong_password() -> None:
    session = FakeSession()
    service = AuthService(session)
    service._users = MagicMock()
    service._users.get_active_by_email = AsyncMock(
        return_value=_make_user(password_hash=hash_password("S3cure!pass"))
    )

    with pytest.raises(AppError) as exc_info:
        await service.login(
            LoginRequest(email="owner@example.com", password="wrong-password")
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.code == "auth.invalid_credentials"


@pytest.mark.asyncio
async def test_login_rejects_unknown_email() -> None:
    session = FakeSession()
    service = AuthService(session)
    service._users = MagicMock()
    service._users.get_active_by_email = AsyncMock(return_value=None)

    with pytest.raises(AppError) as exc_info:
        await service.login(
            LoginRequest(email="ghost@example.com", password="whatever-pass")
        )

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_login_rejects_user_without_password_hash() -> None:
    session = FakeSession()
    service = AuthService(session)
    service._users = MagicMock()
    service._users.get_active_by_email = AsyncMock(
        return_value=_make_user(password_hash=None)
    )

    with pytest.raises(AppError) as exc_info:
        await service.login(
            LoginRequest(email="owner@example.com", password="whatever-pass")
        )

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_refresh_rejects_invalid_token() -> None:
    session = FakeSession()
    service = AuthService(session)
    service._users = MagicMock()
    service._tokens = MagicMock()
    service._tokens.get_any = AsyncMock(return_value=None)

    with pytest.raises(AppError) as exc_info:
        await service.refresh("not-a-real-token")

    assert exc_info.value.status_code == 401
    assert exc_info.value.code == "auth.invalid_refresh_token"


@pytest.mark.asyncio
async def test_refresh_rotates_token() -> None:
    session = FakeSession()
    service = AuthService(session)
    service._users = MagicMock()
    service._tokens = MagicMock()
    service._users.get = AsyncMock(return_value=_make_user())
    family_id = uuid.uuid4()
    service._tokens.get_any = AsyncMock(
        return_value=RefreshToken(
            user_id=uuid.uuid4(),
            organization_id=ORG_ID,
            token_hash="deadbeef",
            family_id=family_id,
            expires_at=utcnow() + timedelta(days=1),
        )
    )
    service._tokens.add = MagicMock()
    service._tokens.mark_replaced = AsyncMock()

    result = await service.refresh("a-valid-raw-token")

    assert result.access_token
    assert service._tokens.mark_replaced.await_count == 1
    assert session.committed is True
    # The rotated token must inherit the original family so a later replay of
    # the parent can revoke the whole chain.
    issued = service._tokens.add.call_args.args[0]
    assert issued.family_id == family_id


@pytest.mark.asyncio
async def test_refresh_rejects_inactive_user() -> None:
    session = FakeSession()
    service = AuthService(session)
    service._users = MagicMock()
    service._tokens = MagicMock()
    service._tokens.get_any = AsyncMock(
        return_value=RefreshToken(
            user_id=uuid.uuid4(),
            organization_id=ORG_ID,
            token_hash="deadbeef",
            expires_at=utcnow() + timedelta(days=1),
        )
    )
    service._users.get = AsyncMock(return_value=_make_user(is_active=False))

    with pytest.raises(AppError) as exc_info:
        await service.refresh("a-valid-raw-token")

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_refresh_detects_reuse_and_revokes_family() -> None:
    session = FakeSession()
    service = AuthService(session)
    service._users = MagicMock()
    service._tokens = MagicMock()
    victim = _make_user()
    service._users.get = AsyncMock(return_value=victim)
    family_id = uuid.uuid4()
    service._tokens.get_any = AsyncMock(
        return_value=RefreshToken(
            user_id=victim.id,
            organization_id=ORG_ID,
            token_hash="rotated",
            family_id=family_id,
            expires_at=utcnow() + timedelta(days=1),
            revoked_at=utcnow(),
        )
    )
    service._tokens.revoke_family = AsyncMock(return_value=3)

    with pytest.raises(AppError) as exc_info:
        await service.refresh("leaked-raw-token")

    assert exc_info.value.status_code == 401
    assert exc_info.value.code == "auth.refresh_token_reuse"
    service._tokens.revoke_family.assert_awaited_once()
    assert service._tokens.revoke_family.await_args.args[0] == family_id
    # Access tokens for the user are invalidated by bumping the token version.
    assert victim.token_version == 1
    assert session.committed is True


@pytest.mark.asyncio
async def test_change_password_requires_correct_current() -> None:
    session = FakeSession()
    service = AuthService(session)
    user = _make_user(password_hash=hash_password("old-password"))

    with pytest.raises(AppError) as exc_info:
        await service.change_password(user, "wrong-old", "new-password")

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "auth.wrong_password"


@pytest.mark.asyncio
async def test_change_password_rotates_hash_and_revokes_tokens() -> None:
    session = FakeSession()
    service = AuthService(session)
    service._tokens = MagicMock()
    service._tokens.revoke_all_for_user = AsyncMock()
    user = _make_user(password_hash=hash_password("old-password"))
    user.token_version = 0

    await service.change_password(user, "old-password", "new-password")

    assert verify_password("new-password", user.password_hash)
    assert not verify_password("old-password", user.password_hash)
    assert user.token_version == 1
    service._tokens.revoke_all_for_user.assert_awaited_once()
    assert session.committed is True


@pytest.mark.asyncio
async def test_logout_revokes_all_tokens_and_bumps_token_version() -> None:
    session = FakeSession()
    service = AuthService(session)
    service._tokens = MagicMock()
    service._tokens.revoke_all_for_user = AsyncMock()
    user = _make_user()
    user.token_version = 0

    await service.logout(user)

    service._tokens.revoke_all_for_user.assert_awaited_once()
    assert user.token_version == 1
    assert session.committed is True


@pytest.mark.asyncio
async def test_login_locks_account_after_repeated_failures() -> None:
    session = FakeSession()
    service = AuthService(session)
    service._users = MagicMock()
    user = _make_user(password_hash=hash_password("S3cure!pass"))
    user.failed_login_attempts = 4  # next failure crosses the threshold
    service._users.get_active_by_email = AsyncMock(return_value=user)

    with pytest.raises(AppError) as exc_info:
        await service.login(LoginRequest(email="owner@example.com", password="wrongpass"))

    assert exc_info.value.status_code == 401
    assert user.failed_login_attempts == 5
    assert user.locked_until is not None
    assert session.committed is True

    # A subsequent incorrect attempt is throttled with Retry-After.
    with pytest.raises(AppError) as locked:
        await service.login(LoginRequest(email="owner@example.com", password="wrongpass"))
    assert locked.value.status_code == 429
    assert locked.value.code == "auth.too_many_attempts"
    assert locked.value.headers and "Retry-After" in locked.value.headers


@pytest.mark.asyncio
async def test_login_correct_password_succeeds_even_when_locked() -> None:
    """An attacker cannot lock a victim out: a correct password always works."""
    session = FakeSession()
    service = AuthService(session)
    service._users = MagicMock()
    service._tokens = MagicMock()
    service._tokens.add = MagicMock()
    user = _make_user(password_hash=hash_password("S3cure!pass"))
    user.failed_login_attempts = 10
    user.locked_until = utcnow() + timedelta(minutes=5)
    service._users.get_active_by_email = AsyncMock(return_value=user)

    result = await service.login(
        LoginRequest(email="owner@example.com", password="S3cure!pass")
    )

    assert result.access_token
    assert user.failed_login_attempts == 0
    assert user.locked_until is None


@pytest.mark.asyncio
async def test_issue_tokens_embeds_token_version_claim() -> None:
    from app.core.security import decode_access_token

    session = FakeSession()
    service = AuthService(session)
    service._tokens = MagicMock()
    service._tokens.add = MagicMock()
    user = _make_user()
    user.token_version = 7

    access, _refresh, _record = await service._issue_tokens(user)
    payload = decode_access_token(access)

    assert payload["tv"] == 7
    assert payload["sub"] == str(user.id)


# ---------------------------------------------------------------------------
# LeadService
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lead_create_sets_defaults(monkeypatch) -> None:
    session = FakeSession()
    service = LeadService(session)
    service._leads = MagicMock()
    service._leads.add = MagicMock()

    auto = MagicMock()
    auto.auto_assign = AsyncMock()
    monkeypatch.setattr("app.services.lead_service.AssignmentService", lambda s: auto)
    pipeline = MagicMock()
    pipeline.reconcile = AsyncMock()
    monkeypatch.setattr("app.services.lead_service.PipelineService", lambda s: pipeline)

    lead = await service.create(
        ORG_ID,
        {"email": "prospect@example.com", "first_name": "Ada"},
    )

    assert lead.status is LeadStatus.NEW
    assert lead.score == 0
    assert lead.email == "prospect@example.com"
    pipeline.reconcile.assert_awaited_once()
    auto.auto_assign.assert_awaited_once()
    assert session.committed is True


@pytest.mark.asyncio
async def test_lead_soft_delete_missing_raises_404() -> None:
    session = FakeSession()
    service = LeadService(session)
    service._leads = MagicMock()
    service._leads.soft_delete = AsyncMock(return_value=False)

    with pytest.raises(AppError) as exc_info:
        await service.soft_delete(ORG_ID, LEAD_ID)

    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "lead.not_found"


@pytest.mark.asyncio
async def test_lead_soft_delete_success() -> None:
    session = FakeSession()
    service = LeadService(session)
    service._leads = MagicMock()
    service._leads.soft_delete = AsyncMock(return_value=True)

    await service.soft_delete(ORG_ID, LEAD_ID)

    assert session.committed is True


@pytest.mark.asyncio
async def test_lead_update_to_won_delegates_reconcile(monkeypatch) -> None:
    session = FakeSession()
    service = LeadService(session)
    service._leads = MagicMock()
    lead = Lead(organization_id=ORG_ID, email="won@example.com", status=LeadStatus.NEW)
    lead.id = uuid.uuid4()
    service._leads.get_or_404 = AsyncMock(return_value=lead)
    pipeline = MagicMock()

    async def _apply_status(_org, _lead, **kw):
        if kw.get("status") is not None:
            _lead.status = kw["status"]

    # Faithful to production: reconcile owns the status transition.
    pipeline.reconcile = AsyncMock(side_effect=_apply_status)
    monkeypatch.setattr("app.services.lead_service.PipelineService", lambda s: pipeline)

    await service.update(ORG_ID, LEAD_ID, {"status": LeadStatus.WON})

    assert lead.status is LeadStatus.WON
    pipeline.reconcile.assert_awaited_once()
    _args, kwargs = pipeline.reconcile.await_args
    assert kwargs["status"] is LeadStatus.WON
    assert kwargs["stage_id"] is None
    assert kwargs["emit_events"] is True
    assert session.committed is True


@pytest.mark.asyncio
async def test_lead_update_open_status_skips_transition_event(monkeypatch) -> None:
    session = FakeSession()
    service = LeadService(session)
    service._leads = MagicMock()
    lead = Lead(organization_id=ORG_ID, email="x@example.com", status=LeadStatus.CONTACTED)
    service._leads.get_or_404 = AsyncMock(return_value=lead)
    pipeline = MagicMock()
    pipeline.reconcile = AsyncMock()
    monkeypatch.setattr("app.services.lead_service.PipelineService", lambda s: pipeline)

    await service.update(ORG_ID, LEAD_ID, {"status": LeadStatus.CONTACTED, "score": 5})

    pipeline.reconcile.assert_awaited_once()
    _args, kwargs = pipeline.reconcile.await_args
    assert kwargs["status"] is LeadStatus.CONTACTED
    assert kwargs["emit_events"] is True
    assert lead.score == 5
    assert session.committed is True


@pytest.mark.asyncio
async def test_lead_update_to_lost_delegates_reconcile(monkeypatch) -> None:
    session = FakeSession()
    service = LeadService(session)
    service._leads = MagicMock()
    lead = Lead(organization_id=ORG_ID, email="lost@example.com", status=LeadStatus.NEW)
    lead.id = uuid.uuid4()
    service._leads.get_or_404 = AsyncMock(return_value=lead)
    pipeline = MagicMock()

    async def _apply_status(_org, _lead, **kw):
        if kw.get("status") is not None:
            _lead.status = kw["status"]

    # Faithful to production: reconcile owns the status transition.
    pipeline.reconcile = AsyncMock(side_effect=_apply_status)
    monkeypatch.setattr("app.services.lead_service.PipelineService", lambda s: pipeline)

    await service.update(ORG_ID, LEAD_ID, {"status": LeadStatus.LOST})

    assert lead.status is LeadStatus.LOST
    pipeline.reconcile.assert_awaited_once()
    _args, kwargs = pipeline.reconcile.await_args
    assert kwargs["status"] is LeadStatus.LOST
    assert kwargs["emit_events"] is True
    assert session.committed is True


# ---------------------------------------------------------------------------
# ConversationService
# ---------------------------------------------------------------------------


def _closed_conversation() -> Conversation:
    conv = Conversation(
        organization_id=ORG_ID,
        lead_id=LEAD_ID,
        channel=OutreachChannel.EMAIL,
        subject="Hello",
        is_open=False,
    )
    conv.last_message_at = None
    return conv


@pytest.mark.asyncio
async def test_add_lead_message_reopens_closed_conversation() -> None:
    session = FakeSession()
    service = ConversationService(session)
    service._conversations = MagicMock()
    service._messages = MagicMock()
    conv = _closed_conversation()
    service._conversations.get_or_404 = AsyncMock(return_value=conv)
    service._messages.add = MagicMock()

    message = await service.add_message(
        ORG_ID, conv.id, {"sender_type": "lead", "body": "Yes, let's talk!"}
    )

    assert conv.is_open is True
    assert conv.last_message_at is not None
    assert message.sender_type is ConversationSender.LEAD
    assert session.committed is True


@pytest.mark.asyncio
async def test_add_agent_message_does_not_reopen_conversation() -> None:
    session = FakeSession()
    service = ConversationService(session)
    service._conversations = MagicMock()
    service._messages = MagicMock()
    conv = _closed_conversation()
    service._conversations.get_or_404 = AsyncMock(return_value=conv)
    service._messages.add = MagicMock()

    await service.add_message(
        ORG_ID, conv.id, {"sender_type": "agent", "body": "Following up"}
    )

    assert conv.is_open is False


# ---------------------------------------------------------------------------
# ImportService
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_create_rejects_second_active_job() -> None:
    session = FakeSession()
    service = ImportService(session)
    service._jobs = MagicMock()
    service._jobs.count_active = AsyncMock(return_value=1)

    with pytest.raises(AppError) as exc_info:
        await service.create(
            ORG_ID, created_by_user_id=uuid.uuid4(), file_name="a.csv", file_size_bytes=10
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "import.active_job_exists"


@pytest.mark.asyncio
async def test_import_create_starts_pending() -> None:
    session = FakeSession()
    service = ImportService(session)
    service._jobs = MagicMock()
    service._jobs.count_active = AsyncMock(return_value=0)
    service._jobs.add = MagicMock()

    job = await service.create(
        ORG_ID, created_by_user_id=uuid.uuid4(), file_name="a.csv", file_size_bytes=10
    )

    assert job.status is ImportStatus.PENDING
    assert job.file_name == "a.csv"
    assert session.committed is True


@pytest.mark.asyncio
async def test_import_cancel_rejects_finished_job() -> None:
    session = FakeSession()
    service = ImportService(session)
    service._jobs = MagicMock()
    from app.models.import_job import ImportJob

    job = ImportJob(
        organization_id=ORG_ID,
        created_by_user_id=uuid.uuid4(),
        status=ImportStatus.COMPLETED,
        file_name="a.csv",
        file_size_bytes=1,
    )
    service._jobs.get_or_404 = AsyncMock(return_value=job)

    with pytest.raises(AppError) as exc_info:
        await service.cancel(ORG_ID, uuid.uuid4())

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "import.not_cancellable"


@pytest.mark.asyncio
async def test_import_cancel_pending_job() -> None:
    session = FakeSession()
    service = ImportService(session)
    service._jobs = MagicMock()
    from app.models.import_job import ImportJob

    job = ImportJob(
        organization_id=ORG_ID,
        created_by_user_id=uuid.uuid4(),
        status=ImportStatus.PENDING,
        file_name="a.csv",
        file_size_bytes=1,
    )
    service._jobs.get_or_404 = AsyncMock(return_value=job)

    await service.cancel(ORG_ID, uuid.uuid4())

    assert job.status is ImportStatus.CANCELLED
    assert job.finished_at is not None
    assert session.committed is True


@pytest.mark.asyncio
async def test_import_persist_upload_rejects_oversized_file(monkeypatch) -> None:
    monkeypatch.setattr("app.services.import_service._MAX_CSV_BYTES", 10)
    session = FakeSession()
    service = ImportService(session)

    with pytest.raises(AppError) as exc_info:
        await service.persist_upload(uuid.uuid4(), b"x" * 11)

    assert exc_info.value.status_code == 413


# ---------------------------------------------------------------------------
# ProviderUsageService
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_provider_usage_record_returns_daily_row() -> None:
    session = FakeSession()
    service = ProviderUsageService(session)
    service._usage = MagicMock()
    service._usage.upsert_daily = AsyncMock()
    record = ProviderUsage(
        organization_id=ORG_ID,
        provider="openai",
        feature="research",
        usage_date=date(2026, 8, 1),
    )
    service._usage.get_daily = AsyncMock(return_value=record)

    result = await service.record(
        ORG_ID,
        provider="openai",
        feature="research",
        usage_date=date(2026, 8, 1),
        request_count=3,
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.01,
    )

    assert result is record
    service._usage.upsert_daily.assert_awaited_once()
    assert session.committed is True
