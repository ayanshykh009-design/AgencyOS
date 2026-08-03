"""Service-layer unit tests: dashboard summary aggregation."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from app.models.enums import LeadStatus
from app.services.dashboard_service import DashboardService

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


def _service() -> DashboardService:
    """Build a dashboard service whose repos are all stubbed out."""
    service = DashboardService(FakeSession())
    service._leads = MagicMock()
    service._users = MagicMock()
    service._conversations = MagicMock()
    service._imports = MagicMock()
    service._attempts = MagicMock()
    service._logs = MagicMock()
    service._usage = MagicMock()
    service._tasks = MagicMock()
    return service


def _wire_counts(service: DashboardService) -> None:
    """Give every repository call a benign default return value."""
    service._leads.funnel = AsyncMock(return_value={status: 0 for status in LeadStatus})
    service._leads.sum_deal_value = AsyncMock(return_value=Decimal("0"))
    service._leads.count_unassigned = AsyncMock(return_value=0)
    service._users.count_by_org = AsyncMock(return_value=0)
    service._users.count_active_by_org = AsyncMock(return_value=0)
    service._conversations.count_open = AsyncMock(return_value=0)
    service._imports.count_active = AsyncMock(return_value=0)
    service._attempts.count_outstanding = AsyncMock(return_value=0)
    service._tasks.count_open = AsyncMock(return_value=0)
    service._tasks.count_overdue = AsyncMock(return_value=0)
    service._tasks.count_due_between = AsyncMock(return_value=0)
    service._tasks.count_completed_since = AsyncMock(return_value=0)
    service._logs.list_entries = AsyncMock(return_value=[])
    service._usage.spend_last_30_days = AsyncMock(return_value=0.0)


def _funnel(**overrides: int) -> dict[LeadStatus, int]:
    funnel = {status: 0 for status in LeadStatus}
    for status, count in overrides.items():
        funnel[LeadStatus(status)] = count
    return funnel


async def test_summary_aggregates_lead_funnel() -> None:
    service = _service()
    _wire_counts(service)
    service._leads.funnel = AsyncMock(
        return_value=_funnel(new=3, won=2, lost=1)
    )

    data = await service.summary(ORG_ID)

    assert data["leads"]["new"] == 3
    assert data["leads"]["won"] == 2
    assert data["leads"]["lost"] == 1
    assert data["leads"]["total"] == 6


async def test_summary_includes_pipeline_metrics() -> None:
    service = _service()
    _wire_counts(service)
    service._leads.funnel = AsyncMock(
        return_value=_funnel(new=1, contacted=2, won=4, lost=3)
    )
    service._leads.sum_deal_value = AsyncMock(return_value=Decimal("1250.50"))
    service._leads.count_unassigned = AsyncMock(return_value=7)

    data = await service.summary(ORG_ID)

    assert data["pipeline"]["won_deals"] == 4
    assert data["pipeline"]["open_deals"] == 3
    assert data["pipeline"]["won_revenue"] == 1250.5
    assert data["pipeline"]["unassigned_leads"] == 7


async def test_summary_includes_task_workload() -> None:
    service = _service()
    _wire_counts(service)
    service._tasks.count_open = AsyncMock(return_value=5)
    service._tasks.count_overdue = AsyncMock(return_value=2)
    service._tasks.count_due_between = AsyncMock(return_value=1)
    service._tasks.count_completed_since = AsyncMock(return_value=9)

    data = await service.summary(ORG_ID)

    assert data["tasks"] == {
        "open": 5,
        "overdue": 2,
        "due_today": 1,
        "completed_30d": 9,
    }


async def test_summary_delegates_user_metrics() -> None:
    service = _service()
    _wire_counts(service)
    service._users.count_by_org = AsyncMock(return_value=12)
    service._users.count_active_by_org = AsyncMock(return_value=10)

    data = await service.summary(ORG_ID)

    assert data["users"] == {"total": 12, "active": 10}


async def test_summary_uses_today_window_for_due_between() -> None:
    service = _service()
    _wire_counts(service)
    captured: dict[str, object] = {}
    service._tasks.count_due_between = AsyncMock(
        side_effect=lambda org, *, start, end: captured.update(
            start=start, end=end
        )
        or 0
    )

    await service.summary(ORG_ID)

    now = datetime.now(UTC)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    assert captured["start"] == start_of_day
    assert captured["end"] == start_of_day + timedelta(days=1)


async def test_summary_includes_remaining_sections() -> None:
    service = _service()
    _wire_counts(service)
    service._conversations.count_open = AsyncMock(return_value=4)
    service._attempts.count_outstanding = AsyncMock(return_value=6)
    service._imports.count_active = AsyncMock(return_value=1)
    service._usage.spend_last_30_days = AsyncMock(return_value=12.34)

    data = await service.summary(ORG_ID)

    assert data["conversations"] == {"open": 4}
    assert data["outreach"] == {"outstanding": 6}
    assert data["imports"] == {"active": 1}
    assert data["activity"] == {"recent": []}
    assert data["usage"] == {"spend_last_30_days_usd": 12.34}
