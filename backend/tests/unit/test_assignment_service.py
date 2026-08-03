"""Service-layer unit tests: lead assignment engine."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.errors import AppError
from app.models.activity_log import ActivityLog
from app.models.assignment import LeadAssignmentLog, LeadAssignmentRule
from app.models.enums import (
    ActivityEventType,
    AssignmentMethod,
    AssignmentStrategy,
    UserRole,
)
from app.models.lead import Lead
from app.models.user import User
from app.services.assignment_service import AssignmentService
from app.services.base import utcnow

ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
LEAD_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")


class FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.committed = False

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        pass


def _make_user(**overrides: object) -> User:
    user = User(
        organization_id=ORG_ID,
        email="member@example.com",
        full_name="Member",
        role=UserRole.SALES_AGENT,
        password_hash=None,
    )
    user.id = uuid.uuid4()
    user.created_at = utcnow()
    user.updated_at = utcnow()
    user.is_active = True
    for key, value in overrides.items():
        setattr(user, key, value)
    return user


def _make_lead(**overrides: object) -> Lead:
    lead = Lead(organization_id=ORG_ID, email="prospect@example.com")
    lead.id = uuid.uuid4()
    lead.created_at = utcnow()
    lead.updated_at = utcnow()
    for key, value in overrides.items():
        setattr(lead, key, value)
    return lead


def _service(session: FakeSession, **repos: object) -> AssignmentService:
    service = AssignmentService(session)
    service._rules = MagicMock()
    service._logs = MagicMock()
    service._leads = MagicMock()
    service._users = MagicMock()
    service._activity = MagicMock()
    for name, fake in repos.items():
        setattr(service, name, fake)
    return service


@pytest.mark.asyncio
async def test_round_robin_auto_assign_distributes() -> None:
    session = FakeSession()
    service = _service(session)
    alice = _make_user()
    bob = _make_user()
    rule = LeadAssignmentRule(
        organization_id=ORG_ID,
        name="RR",
        strategy=AssignmentStrategy.ROUND_ROBIN,
        enabled=True,
        target_user_ids=[str(alice.id), str(bob.id)],
        last_assigned_index=-1,
    )
    service._rules.get = AsyncMock(return_value=rule)
    service._users.list_assignable = AsyncMock(return_value=[alice, bob])
    service._logs.add = MagicMock(side_effect=session.add)
    service._activity.add = MagicMock(side_effect=session.add)

    lead = _make_lead()
    await service.auto_assign(ORG_ID, lead)

    assert lead.owner_user_id == alice.id
    assert rule.last_assigned_index == 0
    log = next(obj for obj in session.added if isinstance(obj, LeadAssignmentLog))
    assert log.method is AssignmentMethod.ROUND_ROBIN
    assert log.to_user_id == alice.id

    lead2 = _make_lead()
    await service.auto_assign(ORG_ID, lead2)
    assert lead2.owner_user_id == bob.id
    assert rule.last_assigned_index == 1


@pytest.mark.asyncio
async def test_manual_strategy_never_auto_assigns() -> None:
    session = FakeSession()
    service = _service(session)
    rule = LeadAssignmentRule(
        organization_id=ORG_ID,
        name="Manual",
        strategy=AssignmentStrategy.MANUAL,
        enabled=True,
        target_user_ids=[],
        last_assigned_index=-1,
    )
    service._rules.get = AsyncMock(return_value=rule)

    lead = _make_lead()
    await service.auto_assign(ORG_ID, lead)

    assert lead.owner_user_id is None


@pytest.mark.asyncio
async def test_disabled_rule_never_auto_assigns() -> None:
    session = FakeSession()
    service = _service(session)
    rule = LeadAssignmentRule(
        organization_id=ORG_ID,
        name="RR",
        strategy=AssignmentStrategy.ROUND_ROBIN,
        enabled=False,
        target_user_ids=[],
        last_assigned_index=-1,
    )
    service._rules.get = AsyncMock(return_value=rule)

    lead = _make_lead()
    await service.auto_assign(ORG_ID, lead)

    assert lead.owner_user_id is None


@pytest.mark.asyncio
async def test_rules_strategy_only_matches_condition() -> None:
    session = FakeSession()
    service = _service(session)
    member = _make_user()
    source_id = uuid.uuid4()
    rule = LeadAssignmentRule(
        organization_id=ORG_ID,
        name="Rules",
        strategy=AssignmentStrategy.RULES,
        enabled=True,
        target_user_ids=[],
        conditions={"source_ids": [str(source_id)]},
        last_assigned_index=-1,
    )
    service._rules.get = AsyncMock(return_value=rule)
    service._users.list_assignable = AsyncMock(return_value=[member])
    service._logs.add = MagicMock(side_effect=session.add)
    service._activity.add = MagicMock(side_effect=session.add)

    # Non-matching source: no assignment.
    other = _make_lead(lead_source_id=uuid.uuid4())
    await service.auto_assign(ORG_ID, other)
    assert other.owner_user_id is None

    # Matching source: assigned.
    match = _make_lead(lead_source_id=source_id)
    await service.auto_assign(ORG_ID, match)
    assert match.owner_user_id == member.id


@pytest.mark.asyncio
async def test_manual_assign_reassigns_and_logs() -> None:
    session = FakeSession()
    service = _service(session)
    actor = _make_user(role=UserRole.ADMIN)
    old_owner = _make_user()
    new_owner = _make_user()
    lead = _make_lead(owner_user_id=old_owner.id)
    service._users.list_assignable = AsyncMock(return_value=[new_owner])
    service._logs.add = MagicMock(side_effect=session.add)
    service._activity.add = MagicMock(side_effect=session.add)

    result = await service.assign(
        ORG_ID, actor, lead, to_user_id=new_owner.id, reason="handoff"
    )

    assert result.owner_user_id == new_owner.id
    logs = [o for o in session.added if isinstance(o, LeadAssignmentLog)]
    assert len(logs) == 1
    assert logs[0].from_user_id == old_owner.id
    assert logs[0].to_user_id == new_owner.id
    assert logs[0].method is AssignmentMethod.MANUAL
    assert logs[0].assigned_by_user_id == actor.id
    activity = [o for o in session.added if isinstance(o, ActivityLog)]
    assert any(e.event_type is ActivityEventType.LEAD_ASSIGNED for e in activity)


@pytest.mark.asyncio
async def test_manual_assign_unassigns() -> None:
    session = FakeSession()
    service = _service(session)
    actor = _make_user(role=UserRole.ADMIN)
    lead = _make_lead(owner_user_id=_make_user().id)
    service._logs.add = MagicMock(side_effect=session.add)
    service._activity.add = MagicMock(side_effect=session.add)

    result = await service.assign(ORG_ID, actor, lead, to_user_id=None)

    assert result.owner_user_id is None
    logs = [o for o in session.added if isinstance(o, LeadAssignmentLog)]
    assert logs[0].method is AssignmentMethod.MANUAL
    assert logs[0].to_user_id is None


@pytest.mark.asyncio
async def test_manual_assign_rejects_invalid_target() -> None:
    session = FakeSession()
    service = _service(session)
    service._users.list_assignable = AsyncMock(return_value=[])
    lead = _make_lead()

    with pytest.raises(AppError) as exc_info:
        await service.assign(
            ORG_ID, _make_user(role=UserRole.ADMIN), lead, to_user_id=uuid.uuid4()
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "assignment.invalid_target"


@pytest.mark.asyncio
async def test_upsert_rule_validates_targets() -> None:
    session = FakeSession()
    service = _service(session)
    service._users.list_assignable = AsyncMock(return_value=[])
    service._rules.get = AsyncMock(return_value=None)

    with pytest.raises(AppError) as exc_info:
        await service.upsert_rule(
            ORG_ID,
            _make_user(role=UserRole.ADMIN),
            name="RR",
            strategy=AssignmentStrategy.ROUND_ROBIN,
            enabled=True,
            target_user_ids=[uuid.uuid4()],
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "assignment.invalid_targets"


@pytest.mark.asyncio
async def test_upsert_rule_creates_when_missing() -> None:
    session = FakeSession()
    service = _service(session)
    member = _make_user()
    service._users.list_assignable = AsyncMock(return_value=[member])
    service._rules.get = AsyncMock(return_value=None)
    service._rules.add = MagicMock(side_effect=session.add)

    rule = await service.upsert_rule(
        ORG_ID,
        _make_user(role=UserRole.ADMIN),
        name="RR",
        strategy=AssignmentStrategy.ROUND_ROBIN,
        enabled=True,
        target_user_ids=[member.id],
    )

    assert rule.strategy is AssignmentStrategy.ROUND_ROBIN
    assert rule.enabled is True
    assert rule.target_user_ids == [str(member.id)]
    assert session.committed is True


@pytest.mark.asyncio
async def test_assign_unassigned_sweep() -> None:
    session = FakeSession()
    service = _service(session)
    alice = _make_user()
    rule = LeadAssignmentRule(
        organization_id=ORG_ID,
        name="RR",
        strategy=AssignmentStrategy.ROUND_ROBIN,
        enabled=True,
        target_user_ids=[str(alice.id)],
        last_assigned_index=-1,
    )
    leads = [_make_lead(), _make_lead(), _make_lead()]
    service._rules.get = AsyncMock(return_value=rule)
    service._users.list_assignable = AsyncMock(return_value=[alice])
    service._leads.list_unassigned = AsyncMock(return_value=leads)
    service._logs.add = MagicMock(side_effect=session.add)

    count = await service.assign_unassigned(ORG_ID)

    assert count == 3
    assert all(lead.owner_user_id == alice.id for lead in leads)
    assert session.committed is True
