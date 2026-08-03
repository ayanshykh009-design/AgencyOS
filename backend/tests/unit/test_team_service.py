"""Service-layer unit tests: team invites and RBAC-protected user updates.

Follows the same pattern as test_services.py: repositories are swapped for
fakes so business rules are verified without a database.
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.config import settings
from app.core.errors import AppError
from app.models.activity_log import ActivityLog
from app.models.enums import ActivityEventType, InviteStatus, UserRole
from app.models.team_invite import TeamInvite
from app.models.user import User
from app.services.base import utcnow
from app.services.team_service import TeamService, _token_hash
from app.services.user_service import UserService

ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


class FakeSession:
    """Minimal async session: records adds; flush/commit/rollback are no-ops."""

    def __init__(self) -> None:
        self.added: list[object] = []
        self.committed = False
        self.rolled_back = False

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


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


def _make_invite(**overrides: object) -> TeamInvite:
    invite = TeamInvite(
        organization_id=ORG_ID,
        email="invitee@example.com",
        full_name="Invitee",
        role=UserRole.MEMBER,
        token_hash=_token_hash("raw-token-value"),
        invited_by_user_id=uuid.uuid4(),
        status=InviteStatus.PENDING,
        expires_at=utcnow() + timedelta(days=7),
    )
    invite.id = uuid.uuid4()
    invite.created_at = utcnow()
    invite.updated_at = utcnow()
    for key, value in overrides.items():
        setattr(invite, key, value)
    return invite


def _service(session: FakeSession, **repos: object) -> TeamService:
    service = TeamService(session)
    service._invites = MagicMock()
    service._users = MagicMock()
    service._orgs = MagicMock()
    service._logs = MagicMock()
    for name, fake in repos.items():
        setattr(service, name, fake)
    return service


# ---------------------------------------------------------------------------
# TeamService.create_invite
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_invite_creates_pending_invite() -> None:
    session = FakeSession()
    service = _service(session)
    service._users.get_by_email = AsyncMock(return_value=None)
    service._invites.get_pending_by_email = AsyncMock(return_value=None)
    service._invites.add = MagicMock(side_effect=session.add)
    service._logs.add = MagicMock(side_effect=session.add)

    invite, raw = await service.create_invite(
        ORG_ID,
        _make_user(),
        email="New@Example.com",
        full_name="New Member",
        role=UserRole.MEMBER,
    )

    assert invite.status is InviteStatus.PENDING
    assert invite.email == "new@example.com"
    assert invite.token_hash == _token_hash(raw)
    assert invite.organization_id == ORG_ID
    assert session.committed is True
    entry = next(obj for obj in session.added if isinstance(obj, ActivityLog))
    assert entry.event_type is ActivityEventType.USER_INVITED


@pytest.mark.asyncio
async def test_create_invite_rejects_owner_role() -> None:
    session = FakeSession()
    service = _service(session)

    with pytest.raises(AppError) as exc_info:
        await service.create_invite(
            ORG_ID,
            _make_user(),
            email="owner@example.com",
            full_name=None,
            role=UserRole.OWNER,
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "team.invite_role_denied"


@pytest.mark.asyncio
async def test_create_invite_rejects_unmanageable_role() -> None:
    session = FakeSession()
    service = _service(session)

    with pytest.raises(AppError) as exc_info:
        await service.create_invite(
            ORG_ID,
            _make_user(role=UserRole.MEMBER),
            email="admin@example.com",
            full_name=None,
            role=UserRole.ADMIN,
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "team.invite_role_denied"


@pytest.mark.asyncio
async def test_create_invite_rejects_existing_user() -> None:
    session = FakeSession()
    service = _service(session)
    service._users.get_by_email = AsyncMock(return_value=_make_user())

    with pytest.raises(AppError) as exc_info:
        await service.create_invite(
            ORG_ID,
            _make_user(),
            email="taken@example.com",
            full_name=None,
            role=UserRole.MEMBER,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "team.user_exists"


@pytest.mark.asyncio
async def test_create_invite_rejects_duplicate_pending() -> None:
    session = FakeSession()
    service = _service(session)
    service._users.get_by_email = AsyncMock(return_value=None)
    service._invites.get_pending_by_email = AsyncMock(return_value=_make_invite())

    with pytest.raises(AppError) as exc_info:
        await service.create_invite(
            ORG_ID,
            _make_user(),
            email="invitee@example.com",
            full_name=None,
            role=UserRole.MEMBER,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "team.invite_exists"


# ---------------------------------------------------------------------------
# TeamService.revoke_invite
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revoke_invite_marks_revoked() -> None:
    session = FakeSession()
    service = _service(session)
    invite = _make_invite()
    service._invites.get_by_org = AsyncMock(return_value=invite)
    service._logs.add = MagicMock(side_effect=session.add)

    result = await service.revoke_invite(ORG_ID, _make_user(), invite.id)

    assert result.status is InviteStatus.REVOKED
    assert result.revoked_at is not None
    assert session.committed is True


@pytest.mark.asyncio
async def test_revoke_invite_rejects_accepted() -> None:
    session = FakeSession()
    service = _service(session)
    invite = _make_invite(status=InviteStatus.ACCEPTED)
    service._invites.get_by_org = AsyncMock(return_value=invite)

    with pytest.raises(AppError) as exc_info:
        await service.revoke_invite(ORG_ID, _make_user(), invite.id)

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "team.invite_not_pending"


# ---------------------------------------------------------------------------
# TeamService.lookup_invite / accept_invite
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lookup_invite_rejects_used_token() -> None:
    session = FakeSession()
    service = _service(session)
    service._invites.get_by_token_hash = AsyncMock(
        return_value=_make_invite(status=InviteStatus.ACCEPTED)
    )

    with pytest.raises(AppError) as exc_info:
        await service.lookup_invite("raw-token-value")

    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "team.invite_invalid"


@pytest.mark.asyncio
async def test_lookup_invite_marks_expired() -> None:
    session = FakeSession()
    service = _service(session)
    service._invites.get_by_token_hash = AsyncMock(
        return_value=_make_invite(expires_at=utcnow() - timedelta(days=1))
    )

    with pytest.raises(AppError) as exc_info:
        await service.lookup_invite("raw-token-value")

    assert exc_info.value.code == "team.invite_expired"
    assert session.committed is True


@pytest.mark.asyncio
async def test_accept_invite_creates_user() -> None:
    session = FakeSession()
    service = _service(session)
    invite = _make_invite()
    service._invites.get_by_token_hash = AsyncMock(return_value=invite)
    service._users.get_by_email = AsyncMock(return_value=None)
    service._users.add = MagicMock(side_effect=session.add)
    service._logs.add = MagicMock(side_effect=session.add)

    result = await service.accept_invite("raw-token-value", "New Member", "S3cure!pass")

    user = next(obj for obj in session.added if isinstance(obj, User))
    assert result.status is InviteStatus.ACCEPTED
    assert result.accepted_user_id == user.id
    assert user.email == "invitee@example.com"
    assert user.role is UserRole.MEMBER
    assert user.password_hash is not None
    assert session.committed is True


@pytest.mark.asyncio
async def test_accept_invite_rejects_taken_email() -> None:
    session = FakeSession()
    service = _service(session)
    invite = _make_invite()
    service._invites.get_by_token_hash = AsyncMock(return_value=invite)
    service._users.get_by_email = AsyncMock(return_value=_make_user())

    with pytest.raises(AppError) as exc_info:
        await service.accept_invite("raw-token-value", "New Member", "S3cure!pass")

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "team.user_exists"


def test_invite_url_uses_frontend_base() -> None:
    assert TeamService.invite_url("abc") == f"{settings.FRONTEND_URL}/invite/abc"


# ---------------------------------------------------------------------------
# UserService.update (RBAC + last-owner safety)
# ---------------------------------------------------------------------------


def _user_service(session: FakeSession, **repos: object) -> UserService:
    service = UserService(session)
    service._users = MagicMock()
    service._logs = MagicMock()
    for name, fake in repos.items():
        setattr(service, name, fake)
    return service


@pytest.mark.asyncio
async def test_update_last_owner_cannot_be_demoted() -> None:
    session = FakeSession()
    service = _user_service(session)
    owner = _make_user(role=UserRole.OWNER)
    service._users.get_or_404 = AsyncMock(return_value=owner)
    service._users.count_active_role = AsyncMock(return_value=1)

    with pytest.raises(AppError) as exc_info:
        await service.update(
            ORG_ID, _make_user(), owner.id, {"role": UserRole.MEMBER}
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "user.last_owner"


@pytest.mark.asyncio
async def test_update_owner_demotion_allowed_with_second_owner() -> None:
    session = FakeSession()
    service = _user_service(session)
    owner = _make_user(role=UserRole.OWNER)
    actor = _make_user(role=UserRole.OWNER)
    service._users.get_or_404 = AsyncMock(return_value=owner)
    service._users.count_active_role = AsyncMock(return_value=2)
    service._logs.add = MagicMock(side_effect=session.add)

    result = await service.update(
        ORG_ID, actor, owner.id, {"role": UserRole.MEMBER}
    )

    assert result.role is UserRole.MEMBER
    assert session.committed is True
    entry = next(obj for obj in session.added if isinstance(obj, ActivityLog))
    assert entry.event_type is ActivityEventType.USER_ROLE_CHANGED


@pytest.mark.asyncio
async def test_update_rejects_self_role_change() -> None:
    session = FakeSession()
    service = _user_service(session)
    user = _make_user(role=UserRole.ADMIN)
    service._users.get_or_404 = AsyncMock(return_value=user)

    with pytest.raises(AppError) as exc_info:
        await service.update(
            ORG_ID, user, user.id, {"role": UserRole.MEMBER}
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "user.self_role_change"


@pytest.mark.asyncio
async def test_update_rejects_managing_peer() -> None:
    session = FakeSession()
    service = _user_service(session)
    actor = _make_user(role=UserRole.ADMIN)
    peer = _make_user(role=UserRole.ADMIN)
    service._users.get_or_404 = AsyncMock(return_value=peer)

    with pytest.raises(AppError) as exc_info:
        await service.update(
            ORG_ID, actor, peer.id, {"is_active": False}
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "user.manage_denied"


@pytest.mark.asyncio
async def test_update_allows_managing_subordinate() -> None:
    session = FakeSession()
    service = _user_service(session)
    actor = _make_user(role=UserRole.ADMIN)
    target = _make_user(role=UserRole.SALES_AGENT)
    service._users.get_or_404 = AsyncMock(return_value=target)
    service._logs.add = MagicMock(side_effect=session.add)

    result = await service.update(
        ORG_ID, actor, target.id, {"is_active": False}
    )

    assert result.is_active is False
    assert session.committed is True
    entry = next(obj for obj in session.added if isinstance(obj, ActivityLog))
    assert entry.event_type is ActivityEventType.USER_STATUS_CHANGED
