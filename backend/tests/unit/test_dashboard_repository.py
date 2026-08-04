"""Repository-layer tests for the single-statement dashboard snapshot.

No database is available locally, so the tests assert the query contract: one
statement carrying every CTE (all the predicates that used to be ~14 separate
ORM queries), correct bind params, and row→dict shaping.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import TextClause

from app.repositories.dashboard import DashboardRepository

ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


class _Row:
    def __init__(self, values: dict) -> None:
        self._values = values

    def __getitem__(self, key: str):
        return self._values[key]


class _Mappings:
    def __init__(self, values: dict) -> None:
        self._row = _Row(values)

    def one(self) -> _Row:
        return self._row


class _Result:
    def __init__(self, values: dict) -> None:
        self._mappings = _Mappings(values)

    def mappings(self) -> _Mappings:
        return self._mappings


class FakeSession(AsyncSession):
    """AsyncSession stand-in that captures the executed statement."""

    def __init__(self) -> None:
        self.executed_stmt: str = ""
        self.executed_params: dict | None = None

    async def execute(self, stmt, params=None):
        assert isinstance(stmt, TextClause)
        self.executed_stmt = str(stmt)
        self.executed_params = dict(params or {})
        return _Result(_full_row())


def _full_row() -> dict:
    return {
        "new": 0,
        "researching": 0,
        "contacted": 0,
        "meeting_booked": 0,
        "proposal_sent": 0,
        "won": 0,
        "lost": 0,
        "open_deals": 0,
        "unassigned_leads": 0,
        "won_deals": 0,
        "won_revenue": 0,
        "users_total": 0,
        "users_active": 0,
        "conversations_open": 0,
        "outreach_outstanding": 0,
        "imports_active": 0,
        "tasks_open": 0,
        "tasks_overdue": 0,
        "tasks_due_today": 0,
        "tasks_completed_30d": 0,
        "spend_30d": 0,
        "activity_items": [],
    }


async def test_snapshot_is_single_statement_with_all_ctes() -> None:
    session = FakeSession()
    repo = DashboardRepository(session)  # type: ignore[arg-type]

    await repo.summary_snapshot(
        ORG_ID,
        now=datetime.now(UTC),
        start_of_day=datetime.now(UTC),
        end_of_day=datetime.now(UTC),
        since_30d=datetime.now(UTC).date(),
    )

    stmt = session.executed_stmt
    for cte in (
        "lead_funnel",
        "lead_extra",
        "won_stats",
        "user_stats",
        "conversation_stats",
        "outreach_stats",
        "import_stats",
        "task_stats",
        "spend_stats",
        "recent_activity",
    ):
        assert "AS (\n" in stmt and cte in stmt
    assert stmt.count("SELECT") >= 11
    # A single round trip: exactly one statement, no UNIONs / no client-side joins.
    assert "UNION" not in stmt


async def test_snapshot_predicates_mirror_individual_repos() -> None:
    session = FakeSession()
    repo = DashboardRepository(session)  # type: ignore[arg-type]

    await repo.summary_snapshot(
        ORG_ID,
        now=datetime.now(UTC),
        start_of_day=datetime.now(UTC),
        end_of_day=datetime.now(UTC),
        since_30d=datetime.now(UTC).date(),
    )

    stmt = session.executed_stmt
    assert "deleted_at IS NULL" in stmt
    assert "status = 'won'" in stmt
    assert "status NOT IN ('won', 'lost')" in stmt
    assert "owner_user_id IS NULL" in stmt
    assert "is_open" in stmt
    assert "status IN ('queued', 'sending')" in stmt
    assert "status IN ('pending', 'processing')" in stmt
    assert "status IN ('todo', 'in_progress')" in stmt
    assert "status = 'completed'" in stmt
    assert "is_active" in stmt
    assert "usage_date >= :since_30d" in stmt
    assert "ORDER BY occurred_at DESC, id DESC" in stmt
    assert "LIMIT 10" in stmt
    assert "jsonb_agg" in stmt


async def test_snapshot_passes_org_and_time_windows() -> None:
    session = FakeSession()
    repo = DashboardRepository(session)  # type: ignore[arg-type]
    now = datetime(2026, 8, 4, 12, 0, 0, tzinfo=UTC)
    start = datetime(2026, 8, 4, 0, 0, 0, tzinfo=UTC)
    end = datetime(2026, 8, 5, 0, 0, 0, tzinfo=UTC)
    since = datetime(2026, 7, 5, tzinfo=UTC).date()

    await repo.summary_snapshot(
        ORG_ID, now=now, start_of_day=start, end_of_day=end, since_30d=since
    )

    assert session.executed_params["org_id"] == ORG_ID
    assert session.executed_params["now"] == now
    assert session.executed_params["start_of_day"] == start
    assert session.executed_params["end_of_day"] == end
    assert session.executed_params["since_30d"] == since


async def test_snapshot_shapes_row_into_named_sections() -> None:
    session = FakeSession()
    repo = DashboardRepository(session)  # type: ignore[arg-type]

    snapshot = await repo.summary_snapshot(
        ORG_ID,
        now=datetime.now(UTC),
        start_of_day=datetime.now(UTC),
        end_of_day=datetime.now(UTC),
        since_30d=datetime.now(UTC).date(),
    )

    assert set(snapshot) == {
        "funnel",
        "users",
        "conversations",
        "outreach",
        "imports",
        "tasks",
        "pipeline",
        "spend_30d",
        "recent_activity",
    }
    assert set(snapshot["funnel"]) == {
        "new", "researching", "contacted", "meeting_booked",
        "proposal_sent", "won", "lost",
    }
    assert set(snapshot["pipeline"]) == {
        "won_deals", "open_deals", "won_revenue", "unassigned_leads",
    }
