"""Service-layer unit tests: dashboard summary aggregation."""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

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


def _snapshot(**overrides) -> dict:
    """A realistic single-round-trip snapshot row from the repository."""
    base = {
        "funnel": {
            status: 0
            for status in (
                "new", "researching", "contacted", "meeting_booked",
                "proposal_sent", "won", "lost",
            )
        },
        "users": {"total": 0, "active": 0},
        "conversations": {"open": 0},
        "outreach": {"outstanding": 0},
        "imports": {"active": 0},
        "tasks": {"open": 0, "overdue": 0, "due_today": 0, "completed_30d": 0},
        "pipeline": {
            "won_deals": 0,
            "open_deals": 0,
            "won_revenue": 0.0,
            "unassigned_leads": 0,
        },
        "spend_30d": 0.0,
        "recent_activity": [],
    }
    base.update(overrides)
    return base


def _service() -> DashboardService:
    """Build a dashboard service whose repository is stubbed out."""
    service = DashboardService(FakeSession())
    service._dashboard = MagicMock()
    return service


async def test_summary_aggregates_lead_funnel() -> None:
    service = _service()
    service._dashboard.summary_snapshot = AsyncMock(
        return_value=_snapshot(
            funnel={"new": 3, "won": 2, "lost": 1, **{
                s: 0 for s in ("researching", "contacted", "meeting_booked", "proposal_sent")
            }}
        )
    )

    data = await service.summary(ORG_ID)

    assert data["leads"]["new"] == 3
    assert data["leads"]["won"] == 2
    assert data["leads"]["lost"] == 1
    assert data["leads"]["total"] == 6


async def test_summary_includes_pipeline_metrics() -> None:
    service = _service()
    service._dashboard.summary_snapshot = AsyncMock(
        return_value=_snapshot(
            funnel={"new": 1, "contacted": 2, "won": 4, "lost": 3, **{
                s: 0 for s in ("researching", "meeting_booked", "proposal_sent")
            }},
            pipeline={
                "won_deals": 4,
                "open_deals": 3,
                "won_revenue": Decimal("1250.50"),
                "unassigned_leads": 7,
            },
        )
    )

    data = await service.summary(ORG_ID)

    assert data["pipeline"]["won_deals"] == 4
    assert data["pipeline"]["open_deals"] == 3
    assert data["pipeline"]["won_revenue"] == 1250.5
    assert data["pipeline"]["unassigned_leads"] == 7


async def test_summary_includes_task_workload() -> None:
    service = _service()
    service._dashboard.summary_snapshot = AsyncMock(
        return_value=_snapshot(
            tasks={"open": 5, "overdue": 2, "due_today": 1, "completed_30d": 9}
        )
    )

    data = await service.summary(ORG_ID)

    assert data["tasks"] == {
        "open": 5,
        "overdue": 2,
        "due_today": 1,
        "completed_30d": 9,
    }


async def test_summary_includes_user_metrics() -> None:
    service = _service()
    service._dashboard.summary_snapshot = AsyncMock(
        return_value=_snapshot(users={"total": 12, "active": 10})
    )

    data = await service.summary(ORG_ID)

    assert data["users"] == {"total": 12, "active": 10}


async def test_summary_uses_today_window_for_due_between() -> None:
    service = _service()
    captured: dict[str, object] = {}
    service._dashboard.summary_snapshot = AsyncMock(
        side_effect=lambda org, **kwargs: captured.update(kwargs)
        or _snapshot()
    )

    await service.summary(ORG_ID)

    now = datetime.now(UTC)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    assert captured["start_of_day"] == start_of_day
    assert captured["end_of_day"] == start_of_day + timedelta(days=1)
    assert captured["since_30d"] == (now - timedelta(days=30)).date()
    assert isinstance(captured["since_30d"], date)
    # `now` comes from the service's own clock; assert near-now within 5s.
    assert abs((captured["now"] - now).total_seconds()) < 5  # type: ignore[operator]


async def test_summary_includes_remaining_sections() -> None:
    service = _service()
    service._dashboard.summary_snapshot = AsyncMock(
        return_value=_snapshot(
            conversations={"open": 4},
            outreach={"outstanding": 6},
            imports={"active": 1},
            spend_30d=12.34,
            recent_activity=[{"id": "abc", "event_type": "lead_created"}],
        )
    )

    data = await service.summary(ORG_ID)

    assert data["conversations"] == {"open": 4}
    assert data["outreach"] == {"outstanding": 6}
    assert data["imports"] == {"active": 1}
    assert data["activity"] == {"recent": [{"id": "abc", "event_type": "lead_created"}]}
    assert data["usage"] == {"spend_last_30_days_usd": 12.34}
