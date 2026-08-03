"""Service-layer unit tests: pipeline stages, close reasons, transitions."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.errors import AppError
from app.models.activity_log import ActivityLog
from app.models.close_reason import CloseReason
from app.models.enums import ActivityEventType, LeadStatus, StageLifecycle, UserRole
from app.models.lead import Lead
from app.models.pipeline_stage import PipelineStage
from app.models.user import User
from app.services.base import utcnow
from app.services.pipeline_service import PipelineService

ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


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


def _make_stage(name: str, lifecycle: StageLifecycle, **overrides: object) -> PipelineStage:
    stage = PipelineStage(
        organization_id=ORG_ID,
        name=name,
        lifecycle=lifecycle,
        position=0,
        is_default=False,
    )
    stage.id = uuid.uuid4()
    for key, value in overrides.items():
        setattr(stage, key, value)
    return stage


def _make_reason(name: str, lifecycle: StageLifecycle, **overrides: object) -> CloseReason:
    reason = CloseReason(organization_id=ORG_ID, lifecycle=lifecycle, name=name)
    reason.id = uuid.uuid4()
    for key, value in overrides.items():
        setattr(reason, key, value)
    return reason


def _make_lead(status: LeadStatus = LeadStatus.NEW, **overrides: object) -> Lead:
    lead = Lead(organization_id=ORG_ID, email="prospect@example.com", status=status)
    lead.id = uuid.uuid4()
    for key, value in overrides.items():
        setattr(lead, key, value)
    return lead


def _make_user(**overrides: object) -> User:
    user = User(
        organization_id=ORG_ID,
        email="owner@example.com",
        full_name="Owner",
        role=UserRole.ADMIN,
        password_hash=None,
    )
    user.id = uuid.uuid4()
    user.is_active = True
    for key, value in overrides.items():
        setattr(user, key, value)
    return user


def _service(session: FakeSession, **repos: object) -> PipelineService:
    service = PipelineService(session)
    service._stages = MagicMock()
    service._reasons = MagicMock()
    service._leads = MagicMock()
    service._activity = MagicMock()
    for name, fake in repos.items():
        setattr(service, name, fake)
    return service


def _wire_defaults(service: PipelineService) -> None:
    """Point ensure_defaults' repo reads at empty lists (idempotent no-op)."""
    service._stages.list = AsyncMock(return_value=[])
    service._reasons.list = AsyncMock(return_value=[])


# ---------------------------------------------------------------------------
# ensure_defaults
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_defaults_seeds_stages_and_reasons() -> None:
    session = FakeSession()
    service = _service(session)
    _wire_defaults(service)
    service._stages.add = MagicMock(side_effect=session.add)
    service._reasons.add = MagicMock(side_effect=session.add)

    await service._ensure_defaults(ORG_ID)

    stages = [o for o in session.added if isinstance(o, PipelineStage)]
    reasons = [o for o in session.added if isinstance(o, CloseReason)]
    assert len(stages) == 7
    assert len(reasons) == 4
    assert any(s.name == "new" and s.is_default for s in stages)
    assert any(s.name == "won" and s.lifecycle is StageLifecycle.WON for s in stages)
    assert any(r.name == "Budget" and r.lifecycle is StageLifecycle.LOST for r in reasons)
    positions = [s.position for s in stages]
    assert positions == sorted(positions)


@pytest.mark.asyncio
async def test_ensure_defaults_is_idempotent() -> None:
    session = FakeSession()
    service = _service(session)
    existing = [
        _make_stage("new", StageLifecycle.OPEN, position=0),
        _make_stage("won", StageLifecycle.WON, position=5),
    ]
    service._stages.list = AsyncMock(return_value=existing)
    service._reasons.list = AsyncMock(return_value=[])
    service._stages.add = MagicMock(side_effect=session.add)
    service._reasons.add = MagicMock(side_effect=session.add)

    await service._ensure_defaults(ORG_ID)

    added_stages = [o for o in session.added if isinstance(o, PipelineStage)]
    assert len(added_stages) == 5  # only the missing open/lost ones
    names = {s.name for s in added_stages}
    assert "new" not in names and "won" not in names


# ---------------------------------------------------------------------------
# transitions: reconcile
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_move_to_won_stage_marks_won_and_emits_event() -> None:
    session = FakeSession()
    service = _service(session)
    _wire_defaults(service)
    stage = _make_stage("won", StageLifecycle.WON, is_default=True)
    service._stages.get_or_404 = AsyncMock(return_value=stage)
    service._activity.add = MagicMock(side_effect=session.add)
    lead = _make_lead(LeadStatus.NEW)

    await service.move(ORG_ID, _make_user(), lead, stage_id=stage.id)

    assert lead.stage_id == stage.id
    assert lead.status is LeadStatus.WON
    assert lead.won_at is not None
    assert lead.lost_at is None
    entry = next(o for o in session.added if isinstance(o, ActivityLog))
    assert entry.event_type is ActivityEventType.LEAD_WON
    assert session.committed is True


@pytest.mark.asyncio
async def test_move_to_lost_stage_marks_lost_and_emits_event() -> None:
    session = FakeSession()
    service = _service(session)
    _wire_defaults(service)
    stage = _make_stage("lost", StageLifecycle.LOST, is_default=True)
    service._stages.get_or_404 = AsyncMock(return_value=stage)
    service._activity.add = MagicMock(side_effect=session.add)
    lead = _make_lead(LeadStatus.NEW)

    await service.move(ORG_ID, _make_user(), lead, stage_id=stage.id)

    assert lead.status is LeadStatus.LOST
    assert lead.lost_at is not None
    assert lead.won_at is None
    entry = next(o for o in session.added if isinstance(o, ActivityLog))
    assert entry.event_type is ActivityEventType.LEAD_LOST


@pytest.mark.asyncio
async def test_move_to_open_stage_clears_closure_and_maps_status() -> None:
    session = FakeSession()
    service = _service(session)
    _wire_defaults(service)
    stage = _make_stage("contacted", StageLifecycle.OPEN)
    service._stages.get_or_404 = AsyncMock(return_value=stage)
    service._activity.add = MagicMock(side_effect=session.add)
    lead = _make_lead(
        LeadStatus.WON, won_at=utcnow(), close_reason_id=uuid.uuid4()
    )

    await service.move(ORG_ID, _make_user(), lead, stage_id=stage.id)

    assert lead.status is LeadStatus.CONTACTED
    assert lead.won_at is None
    assert lead.close_reason_id is None
    assert not any(isinstance(o, ActivityLog) for o in session.added)


@pytest.mark.asyncio
async def test_move_keeps_status_when_stage_matches() -> None:
    session = FakeSession()
    service = _service(session)
    _wire_defaults(service)
    stage = _make_stage("proposal_sent", StageLifecycle.OPEN)
    service._stages.get_or_404 = AsyncMock(return_value=stage)
    lead = _make_lead(LeadStatus.PROPOSAL_SENT)

    await service.move(ORG_ID, _make_user(), lead, stage_id=stage.id)

    assert lead.status is LeadStatus.PROPOSAL_SENT


@pytest.mark.asyncio
async def test_move_rejects_unknown_stage() -> None:
    session = FakeSession()
    service = _service(session)
    _wire_defaults(service)
    service._stages.get_or_404 = AsyncMock(
        side_effect=AppError("pipeline.stage_not_found", "Pipeline stage not found", 404)
    )
    lead = _make_lead()

    with pytest.raises(AppError) as exc_info:
        await service.move(ORG_ID, _make_user(), lead, stage_id=uuid.uuid4())

    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "pipeline.stage_not_found"


@pytest.mark.asyncio
async def test_move_rejects_close_reason_lifecycle_mismatch() -> None:
    session = FakeSession()
    service = _service(session)
    _wire_defaults(service)
    won = _make_stage("won", StageLifecycle.WON)
    service._stages.get_or_404 = AsyncMock(return_value=won)
    lost_reason = _make_reason("Budget", StageLifecycle.LOST)
    service._reasons.get = AsyncMock(return_value=lost_reason)
    lead = _make_lead(LeadStatus.NEW)

    with pytest.raises(AppError) as exc_info:
        await service.move(
            ORG_ID, _make_user(), lead, stage_id=won.id, close_reason_id=lost_reason.id
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "pipeline.close_reason_lifecycle_mismatch"


@pytest.mark.asyncio
async def test_move_sets_close_reason_on_won() -> None:
    session = FakeSession()
    service = _service(session)
    _wire_defaults(service)
    won = _make_stage("won", StageLifecycle.WON)
    service._stages.get_or_404 = AsyncMock(return_value=won)
    reason = _make_reason("Contract signed", StageLifecycle.WON)
    service._reasons.get = AsyncMock(return_value=reason)
    service._activity.add = MagicMock(side_effect=session.add)
    lead = _make_lead(LeadStatus.NEW)

    await service.move(ORG_ID, _make_user(), lead, stage_id=won.id, close_reason_id=reason.id)

    assert lead.close_reason_id == reason.id
    assert lead.status is LeadStatus.WON


@pytest.mark.asyncio
async def test_status_change_to_won_aligns_default_stage() -> None:
    session = FakeSession()
    service = _service(session)
    _wire_defaults(service)
    won = _make_stage("won", StageLifecycle.WON, is_default=True)
    service._stages.get = AsyncMock(return_value=None)
    service._stages.get_default = AsyncMock(return_value=won)
    service._activity.add = MagicMock(side_effect=session.add)
    lead = _make_lead(LeadStatus.NEW)

    await service.reconcile(ORG_ID, lead, status=LeadStatus.WON)

    assert lead.status is LeadStatus.WON
    assert lead.stage_id == won.id
    assert lead.won_at is not None
    entry = next(o for o in session.added if isinstance(o, ActivityLog))
    assert entry.event_type is ActivityEventType.LEAD_WON


@pytest.mark.asyncio
async def test_reconcile_no_double_event_on_repeat_won() -> None:
    session = FakeSession()
    service = _service(session)
    _wire_defaults(service)
    won = _make_stage("won", StageLifecycle.WON)
    service._stages.get_or_404 = AsyncMock(return_value=won)
    service._activity.add = MagicMock(side_effect=session.add)
    lead = _make_lead(LeadStatus.WON)

    await service.move(ORG_ID, _make_user(), lead, stage_id=won.id)

    assert not any(isinstance(o, ActivityLog) for o in session.added)


# ---------------------------------------------------------------------------
# stage management
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_stage_appends_position() -> None:
    session = FakeSession()
    service = _service(session)
    existing = [
        _make_stage("new", StageLifecycle.OPEN, position=0),
        _make_stage("contacted", StageLifecycle.OPEN, position=1),
    ]
    service._stages.list = AsyncMock(return_value=existing)
    service._stages.add = MagicMock(side_effect=session.add)

    stage = await service.create_stage(
        ORG_ID, _make_user(), name="Demo call", lifecycle=StageLifecycle.OPEN
    )

    assert stage.position == 2
    assert stage.is_default is False
    assert session.committed is True


@pytest.mark.asyncio
async def test_create_stage_rejects_duplicate_name() -> None:
    session = FakeSession()
    service = _service(session)
    service._stages.list = AsyncMock(
        return_value=[_make_stage("won", StageLifecycle.WON)]
    )

    with pytest.raises(AppError) as exc_info:
        await service.create_stage(ORG_ID, _make_user(), name="won", lifecycle=StageLifecycle.WON)

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "pipeline.stage_exists"


@pytest.mark.asyncio
async def test_delete_stage_moves_leads_to_alternative() -> None:
    session = FakeSession()
    service = _service(session)
    stage = _make_stage("contacted", StageLifecycle.OPEN)
    alternative = _make_stage("new", StageLifecycle.OPEN, is_default=True)
    service._stages.get_or_404 = AsyncMock(return_value=stage)
    service._stages.list = AsyncMock(return_value=[stage, alternative])
    service._stages.delete = AsyncMock()
    service._leads.count_in_stage = AsyncMock(return_value=3)
    service._leads.bulk_move_stage = AsyncMock(return_value=3)

    await service.delete_stage(ORG_ID, stage.id)

    service._leads.bulk_move_stage.assert_awaited_once_with(ORG_ID, stage.id, alternative.id)
    service._stages.delete.assert_awaited_once_with(stage)
    assert session.committed is True


@pytest.mark.asyncio
async def test_delete_stage_with_leads_and_no_alternative_raises() -> None:
    session = FakeSession()
    service = _service(session)
    stage = _make_stage("won", StageLifecycle.WON, is_default=True)
    service._stages.get_or_404 = AsyncMock(return_value=stage)
    service._stages.list = AsyncMock(return_value=[stage])
    service._leads.count_in_stage = AsyncMock(return_value=2)

    with pytest.raises(AppError) as exc_info:
        await service.delete_stage(ORG_ID, stage.id)

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "pipeline.no_alternative_stage"


@pytest.mark.asyncio
async def test_reorder_stages_validates_payload() -> None:
    session = FakeSession()
    service = _service(session)
    a = _make_stage("a", StageLifecycle.OPEN, position=0)
    b = _make_stage("b", StageLifecycle.OPEN, position=1)
    service._stages.list = AsyncMock(return_value=[a, b])

    with pytest.raises(AppError) as exc_info:
        await service.reorder_stages(ORG_ID, [a.id])

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "pipeline.stage_reorder_mismatch"


# ---------------------------------------------------------------------------
# close reasons
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_close_reason_rejects_open_lifecycle() -> None:
    session = FakeSession()
    service = _service(session)

    with pytest.raises(AppError) as exc_info:
        await service.create_close_reason(
            ORG_ID, _make_user(), name="Budget", lifecycle=StageLifecycle.OPEN
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "pipeline.close_reason_invalid_lifecycle"


@pytest.mark.asyncio
async def test_delete_close_reason_blocked_while_in_use() -> None:
    session = FakeSession()
    service = _service(session)
    reason = _make_reason("Budget", StageLifecycle.LOST)
    service._reasons.get_or_404 = AsyncMock(return_value=reason)
    service._leads.count_using_close_reason = AsyncMock(return_value=1)

    with pytest.raises(AppError) as exc_info:
        await service.delete_close_reason(ORG_ID, reason.id)

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "pipeline.close_reason_in_use"
