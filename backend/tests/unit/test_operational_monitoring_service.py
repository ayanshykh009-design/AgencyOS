"""Unit tests for OperationalMonitoringService tenant scoping (B-2).

Every tenant-data aggregate must be filtered by the caller's organization_id
at the service→repository boundary. Worker/process counters are
infrastructure-level and stay global.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

from app.models.enums import ExecutionStatus
from app.services.operational_monitoring_service import OperationalMonitoringService

ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
OTHER_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")


def _service() -> tuple[OperationalMonitoringService, MagicMock]:
    session = MagicMock()
    svc = OperationalMonitoringService(session)
    return svc, session


async def test_get_execution_statistics_scopes_all_repo_calls_to_org() -> None:
    """B-2: execution statistics forward organization_id to every repo call."""
    svc, _ = _service()
    repo = MagicMock()
    repo.count_by_status_and_date = AsyncMock(return_value=1)
    repo.count_by_workflow = AsyncMock(return_value={"wf": 1})
    repo.count_by_organization = AsyncMock(return_value={"Org A": 1})
    svc._execution_repo = repo

    result = await svc.get_execution_statistics(ORG_ID, hours=24)

    assert result["counts_by_status"][ExecutionStatus.QUEUED.value] == 1
    # One call per known execution status, every call org-scoped.
    assert repo.count_by_status_and_date.await_count == 7
    for call in repo.count_by_status_and_date.await_args_list:
        assert call.kwargs.get("organization_id") == ORG_ID
    assert repo.count_by_workflow.await_args.args[1] == ORG_ID
    assert repo.count_by_organization.await_args.args[1] == ORG_ID
    assert result["counts_by_organization"] == {"Org A": 1}


async def test_get_queue_status_scopes_to_single_org() -> None:
    svc, _ = _service()
    repo = MagicMock()
    repo.queue_status = AsyncMock(return_value=[(ORG_ID, "Org A", 2, 1, 3)])
    svc._execution_repo = repo

    result = await svc.get_queue_status(ORG_ID)

    assert repo.queue_status.await_args.args[0] == ORG_ID
    assert result["total_queued"] == 2
    assert result["organization_queues"][0]["organization_id"] == str(ORG_ID)


async def test_get_execution_history_scopes_repo_calls_to_org() -> None:
    svc, _ = _service()
    repo = MagicMock()
    repo.list_history = AsyncMock(return_value=[])
    repo.count_history = AsyncMock(return_value=0)
    svc._execution_repo = repo

    await svc.get_execution_history(ORG_ID, page=1, page_size=10, hours=24)

    assert repo.list_history.await_args.kwargs["organization_id"] == ORG_ID
    assert repo.count_history.await_args.kwargs["organization_id"] == ORG_ID


async def test_get_execution_timeline_scopes_repo_calls_to_org() -> None:
    svc, _ = _service()
    repo = MagicMock()
    repo.list_timeline = AsyncMock(return_value=[])
    svc._execution_repo = repo

    await svc.get_execution_timeline(ORG_ID, hours=24, status=None, workflow_name=None, limit=10)

    assert repo.list_timeline.await_args.kwargs["organization_id"] == ORG_ID


async def test_get_operational_summary_scopes_tenant_data_to_org() -> None:
    """B-2: summary execution/event aggregates are org-scoped; worker stats stay infra."""
    svc, _ = _service()
    exec_repo = MagicMock()
    exec_repo.count_pending = AsyncMock(return_value=5)
    exec_repo.count_status = AsyncMock(return_value=2)
    svc._execution_repo = exec_repo

    event_repo = MagicMock()
    event_repo.count_by_date_range = AsyncMock(return_value=9)
    svc._event_repo = event_repo

    wf_event_repo = MagicMock()
    wf_event_repo.count_events_queued = AsyncMock(return_value=1)
    wf_event_repo.count_events_consumed = AsyncMock(return_value=2)
    svc._workflow_event_repo = wf_event_repo

    automation = MagicMock()
    automation.get_status = AsyncMock(
        return_value=MagicMock(enabled=True, paused_by=None, paused_at=None, paused_reason=None)
    )
    svc._automation_control_service = automation

    worker_service = MagicMock()
    worker_service.list_alive = AsyncMock(return_value=[])
    worker_service.count_stale = AsyncMock(return_value=0)
    svc._worker_service = worker_service

    result = await svc.get_operational_summary(ORG_ID)

    assert exec_repo.count_pending.await_args.args[0] == ORG_ID
    for call in exec_repo.count_status.await_args_list:
        assert call.kwargs.get("organization_id") == ORG_ID
    assert event_repo.count_by_date_range.await_args.kwargs["organization_id"] == ORG_ID
    assert wf_event_repo.count_events_queued.await_args.args[0] == ORG_ID
    assert wf_event_repo.count_events_consumed.await_args.args[0] == ORG_ID
    assert result["executions"]["queued"] == 5


async def test_get_automation_lifecycle_scopes_activity_logs_to_org() -> None:
    svc, _ = _service()
    logs_repo = MagicMock()
    logs_repo.count_by_event_type = AsyncMock(return_value=3)
    svc._logs_repo = logs_repo

    automation = MagicMock()
    automation.get_status = AsyncMock(
        return_value=MagicMock(enabled=True, paused_by=None, paused_at=None, paused_reason=None)
    )
    svc._automation_control_service = automation

    result = await svc.get_automation_lifecycle(ORG_ID)

    assert logs_repo.count_by_event_type.await_count == 2
    for call in logs_repo.count_by_event_type.await_args_list:
        assert call.kwargs.get("organization_id") == ORG_ID
    assert result["automation_paused_events"] == 3


async def test_get_monitoring_information_scopes_queue_to_org() -> None:
    svc, _ = _service()
    exec_repo = MagicMock()
    exec_repo.count_by_status_and_date = AsyncMock(return_value=0)
    exec_repo.count_pending = AsyncMock(return_value=4)
    exec_repo.count_status = AsyncMock(return_value=1)
    svc._execution_repo = exec_repo

    worker_service = MagicMock()
    worker_service.list_alive = AsyncMock(return_value=[])
    svc._worker_service = worker_service

    result = await svc.get_monitoring_information(ORG_ID)

    assert exec_repo.count_pending.await_args.args[0] == ORG_ID
    for call in exec_repo.count_by_status_and_date.await_args_list:
        assert call.kwargs.get("organization_id") == ORG_ID
    assert result["queue"]["total_queued"] == 4
