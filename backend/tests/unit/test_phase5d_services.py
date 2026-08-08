"""Service-layer unit tests for the Phase 5D AI Intelligence Layer services.

Covers the business rules that live in the thin service layer (org scoping,
approval state-machine transitions, read-through on upsert, not-found errors)
without a database — repositories are mocked.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.errors import AppError
from app.models.agent_run import AgentRun
from app.models.agent_state import AgentState
from app.models.approval_log import ApprovalLog
from app.models.approval_request import ApprovalRequest
from app.models.briefing import Briefing
from app.models.enums import (
    AgentHealth,
    AgentRunStatus,
    AgentRunTrigger,
    AgentStateStatus,
    ApprovalLogAction,
    ApprovalRequestStatus,
    BriefingType,
)
from app.models.notification import Notification
from app.services.agent_service import AgentService
from app.services.approval_service import ApprovalService
from app.services.communication_service import CommunicationService, CommunicationSummary
from app.services.founder_service import FounderService
from app.services.growth_service import GrowthService
from app.services.memory_service import MemoryService
from app.services.notification_service import NotificationService

ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
USER_ID = uuid.uuid4()
ACTOR = MagicMock(spec=["id"])
ACTOR.id = USER_ID


class FakeSession:
    def __init__(self) -> None:
        self.committed = False
        self.added: list[object] = []

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        pass

    async def flush(self) -> None:
        pass

    async def refresh(self, instance: object) -> None:
        pass


def _service(service_cls, *repo_attrs: str) -> tuple[FakeSession, object, list]:
    session = FakeSession()
    service = service_cls(session)
    mocks: list = []
    for _i, attr in enumerate(repo_attrs):
        m = MagicMock(name=attr)
        setattr(service, attr, m)
        mocks.append(m)
    return session, service, mocks


# -- AgentService ----------------------------------------------------


@pytest.mark.asyncio
async def test_agent_upsert_state_writes_and_fetches() -> None:
    session, service, mocks = _service(AgentService, "_states")
    states_repo: MagicMock = mocks[0]
    states_repo.upsert = AsyncMock()
    fetched = AgentState(
        id=uuid.uuid4(),
        organization_id=ORG_ID,
        agent_name="a",
        status=AgentStateStatus.ACTIVE,
        health=AgentHealth.HEALTHY,
    )
    states_repo.get_by_name = AsyncMock(return_value=fetched)

    result = await service.upsert_state(
        ORG_ID,
        agent_name="a",
        status=AgentStateStatus.ACTIVE,
        health=AgentHealth.HEALTHY,
        queue_depth=0,
        total_runs=0,
        average_runtime_ms=0,
        average_cost=0,
        last_execution=None,
        last_error=None,
    )

    states_repo.upsert.assert_awaited_once()
    assert session.committed is True
    assert result is fetched


@pytest.mark.asyncio
async def test_agent_upsert_state_errors_when_fetch_returns_none() -> None:
    session, service, mocks = _service(AgentService, "_states")
    states_repo: MagicMock = mocks[0]
    states_repo.upsert = AsyncMock()
    states_repo.get_by_name = AsyncMock(return_value=None)

    with pytest.raises(AppError) as exc:
        await service.upsert_state(
            ORG_ID,
            agent_name="a",
            status=AgentStateStatus.ACTIVE,
            health=AgentHealth.HEALTHY,
            queue_depth=0,
            total_runs=0,
            average_runtime_ms=0,
            average_cost=0,
            last_execution=None,
            last_error=None,
        )
    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_agent_create_run_persists_and_commit() -> None:
    session, service, _ = _service(AgentService, "_states")
    run = await service.create_run(
        ORG_ID,
        agent_name="a",
        status=AgentRunStatus.QUEUED,
        trigger=AgentRunTrigger.MANUAL,
        workflow_id=None,
        input_={},
    )
    assert run.organization_id == ORG_ID
    assert run.agent_name == "a"
    assert session.committed is True
    assert any(isinstance(o, AgentRun) for o in session.added)


@pytest.mark.asyncio
async def test_agent_update_run_not_found_404() -> None:
    session, service, _ = _service(AgentService, "_states")
    runs: MagicMock = MagicMock()
    runs.get_or_404 = AsyncMock(
        side_effect=AppError("agent_run.not_found", "Not found", 404)
    )
    service._runs = runs
    with pytest.raises(AppError) as exc:
        await service.update_run(ORG_ID, uuid.uuid4(), status=AgentRunStatus.SUCCEEDED)
    assert exc.value.status_code == 404


# -- MemoryService ---------------------------------------------------


@pytest.mark.asyncio
async def test_memory_delete_not_found_404() -> None:
    session, service, mocks = _service(MemoryService, "_memories")
    memories: MagicMock = mocks[0]
    memories.delete = AsyncMock(return_value=False)
    with pytest.raises(AppError) as exc:
        await service.delete_memory(ORG_ID, uuid.uuid4())
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_memory_search_strips_and_calls_repo() -> None:
    session, service, mocks = _service(MemoryService, "_knowledge")
    knowledge: MagicMock = mocks[0]
    knowledge.search = AsyncMock(return_value=[])
    await service.search_knowledge(ORG_ID, query="  lead  ", limit=50)
    knowledge.search.assert_awaited_once_with(ORG_ID, query="lead", limit=50)


@pytest.mark.asyncio
async def test_memory_search_blank_rejected() -> None:
    session, service, mocks = _service(MemoryService, "_knowledge")
    with pytest.raises(AppError) as exc:
        await service.search_knowledge(ORG_ID, query="   ")
    assert exc.value.status_code == 400


# -- NotificationService ---------------------------------------------


@pytest.mark.asyncio
async def test_notification_get_for_user_404_when_not_owned() -> None:
    session, service, _ = _service(NotificationService)
    notifications: MagicMock = MagicMock()
    notifications.get = AsyncMock(return_value=Notification(
        organization_id=ORG_ID, user_id=uuid.uuid4()
    ))
    service._notifications = notifications
    with pytest.raises(AppError) as exc:
        await service.get_for_user(ORG_ID, uuid.uuid4(), uuid.uuid4())
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_notification_set_read_not_found_404() -> None:
    session, service, mocks = _service(NotificationService, "_notifications")
    notifications: MagicMock = mocks[0]
    notifications.set_read = AsyncMock(return_value=False)
    with pytest.raises(AppError) as exc:
        await service.set_read(ORG_ID, USER_ID, uuid.uuid4(), is_read=True)
    assert exc.value.status_code == 404


# -- ApprovalService -------------------------------------------------


@pytest.mark.asyncio
async def test_approval_decide_transitions_and_logs() -> None:
    session, service, mocks = _service(ApprovalService, "_requests", "_logs")
    requests_repo, logs_repo = mocks
    requests_repo.get_or_404 = AsyncMock(return_value=ApprovalRequest(
        organization_id=ORG_ID,
        requested_by_user_id=uuid.uuid4(),
        approver_user_id=uuid.uuid4(),
        title="t",
        status=ApprovalRequestStatus.PENDING,
    ))
    logs_repo.add = MagicMock(side_effect=session.add)

    result = await service.decide(
        ORG_ID, ACTOR, uuid.uuid4(), approve=True, decided_by_user_id=None,
        decision_note="looks good",
    )

    assert result.status is ApprovalRequestStatus.APPROVED
    assert session.committed is True
    appended = next(o for o in session.added if isinstance(o, ApprovalLog))
    assert appended.action is ApprovalLogAction.APPROVED
    assert appended.actor_user_id == USER_ID


@pytest.mark.asyncio
async def test_approval_decide_rejects_non_pending() -> None:
    session, service, mocks = _service(ApprovalService, "_requests", "_logs")
    requests_repo, _ = mocks
    requests_repo.get_or_404 = AsyncMock(return_value=ApprovalRequest(
        organization_id=ORG_ID, title="t", status=ApprovalRequestStatus.APPROVED,
    ))
    with pytest.raises(AppError) as exc:
        await service.decide(ORG_ID, ACTOR, uuid.uuid4(), approve=True,
                             decided_by_user_id=uuid.uuid4(), decision_note=None)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_approval_create_request_appends_requested_log() -> None:
    session, service, mocks = _service(ApprovalService, "_requests", "_logs")
    requests_repo, logs_repo = mocks
    requests_repo.add = MagicMock(side_effect=session.add)
    logs_repo.add = MagicMock(side_effect=session.add)

    await service.create_request(
        ORG_ID, requested_by_user_id=USER_ID, actor=ACTOR,
        workflow_id=None, workflow_execution_id=None, approver_user_id=None,
        title="Ship", details=None, expires_at=None,
    )

    assert any(isinstance(o, ApprovalRequest) for o in session.added)
    log = next(o for o in session.added if isinstance(o, ApprovalLog))
    assert log.action is ApprovalLogAction.REQUESTED


# -- FounderService --------------------------------------------------


@pytest.mark.asyncio
async def test_founder_latest_briefing_404_when_none() -> None:
    session, service, mocks = _service(FounderService, "_briefings")
    briefings: MagicMock = mocks[0]
    briefings.latest_by_type = AsyncMock(return_value=None)
    with pytest.raises(AppError) as exc:
        await service.latest_briefing(ORG_ID, BriefingType.DAILY)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_founder_delete_insight_not_found_404() -> None:
    session, service, mocks = _service(FounderService, "_insights")
    insights: MagicMock = mocks[0]
    insights.delete = AsyncMock(return_value=False)
    with pytest.raises(AppError) as exc:
        await service.delete_insight(ORG_ID, uuid.uuid4())
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_founder_insight_counts_aggregates() -> None:
    session, service = _service(FounderService, "_insights")[0:2]
    insights: MagicMock = service._insights
    insights.count_open = AsyncMock(return_value=3)
    insights.count_by_type = AsyncMock(return_value={"opportunity": 3})
    open_count, by_type = await service.insight_counts(ORG_ID)
    assert open_count == 3
    assert by_type == {"opportunity": 3}


# -- GrowthService ---------------------------------------------------


@pytest.mark.asyncio
async def test_growth_latest_forecast_404_when_none() -> None:
    session, service, mocks = _service(GrowthService, "_forecasts")
    forecasts: MagicMock = mocks[0]
    forecasts.latest_by_type = AsyncMock(return_value=None)
    with pytest.raises(AppError) as exc:
        await service.latest_forecast(ORG_ID, "revenue")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_growth_create_metric_persists() -> None:
    session, service, mocks = _service(GrowthService, "_metrics", "_forecasts")
    metrics: MagicMock = mocks[0]
    metrics.add = MagicMock()
    metric = await service.create_metric(
        ORG_ID, metric_type="revenue", period_start=uuid.uuid4(),
        period_end=uuid.uuid4(), value=10, unit="usd", metadata_={},
    )
    assert metric.organization_id == ORG_ID
    assert session.committed is True


# -- CommunicationService --------------------------------------------


@pytest.mark.asyncio
async def test_communication_summary_aggregates_sources() -> None:
    session, service = _service(
        CommunicationService, "_notifications", "_approvals", "_insights", "_briefings"
    )[0:2]
    service._notifications.count_unread = AsyncMock(return_value=2)
    service._approvals.count_pending = AsyncMock(return_value=1)
    service._insights.count_open = AsyncMock(return_value=5)
    briefing = Briefing(
        id=uuid.uuid4(),
        organization_id=ORG_ID,
        briefing_type=BriefingType.DAILY,
        title="d",
        summary="s",
    )
    service._briefings.latest_by_type = AsyncMock(return_value=briefing)

    summary = await service.summary(ORG_ID, USER_ID)
    assert isinstance(summary, CommunicationSummary)
    assert summary.unread_notifications == 2
    assert summary.pending_approvals == 1
    assert summary.active_insights == 5
    assert summary.latest_briefing is briefing
