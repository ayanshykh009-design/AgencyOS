"""Dashboard repository: a single-statement aggregate snapshot.

The dashboard landing page needs ~14 counters across 8 tables. Running them as
separate ORM queries serializes ~14 round trips per request; instead this
repository folds every counter (plus the recent-activity feed) into one SQL
statement built from WITH (CTE) blocks, so the whole snapshot arrives in a
single round trip. Predicates mirror the individual repository methods they
replace (``LeadRepository.funnel``, ``TaskRepository.count_*``, etc.).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# All CTEs are single-row aggregates except ``recent_activity`` which collapses
# its feed into one JSON array; the final SELECT is therefore always exactly one
# row regardless of whether any table is empty.
_SUMMARY_SQL = text(
    """
    WITH lead_funnel AS (
        SELECT
            count(*) FILTER (WHERE status = 'new')            AS new,
            count(*) FILTER (WHERE status = 'researching')    AS researching,
            count(*) FILTER (WHERE status = 'contacted')      AS contacted,
            count(*) FILTER (WHERE status = 'meeting_booked') AS meeting_booked,
            count(*) FILTER (WHERE status = 'proposal_sent')  AS proposal_sent,
            count(*) FILTER (WHERE status = 'won')            AS won,
            count(*) FILTER (WHERE status = 'lost')           AS lost
        FROM leads
        WHERE organization_id = :org_id AND deleted_at IS NULL
    ),
    lead_extra AS (
        SELECT
            count(*) FILTER (WHERE status NOT IN ('won', 'lost')) AS open_deals,
            count(*) FILTER (WHERE owner_user_id IS NULL)         AS unassigned_leads
        FROM leads
        WHERE organization_id = :org_id AND deleted_at IS NULL
    ),
    won_stats AS (
        SELECT
            count(*)                  AS won_deals,
            coalesce(sum(deal_value), 0) AS won_revenue
        FROM leads
        WHERE organization_id = :org_id AND deleted_at IS NULL AND status = 'won'
    ),
    user_stats AS (
        SELECT
            count(*)                                   AS total,
            count(*) FILTER (WHERE is_active)          AS active
        FROM users
        WHERE organization_id = :org_id
    ),
    conversation_stats AS (
        SELECT count(*) AS open
        FROM conversations
        WHERE organization_id = :org_id AND is_open
    ),
    outreach_stats AS (
        SELECT count(*) AS outstanding
        FROM outreach_attempts
        WHERE organization_id = :org_id AND status IN ('queued', 'sending')
    ),
    import_stats AS (
        SELECT count(*) AS active
        FROM import_jobs
        WHERE organization_id = :org_id AND status IN ('pending', 'processing')
    ),
    task_stats AS (
        SELECT
            count(*) FILTER (
                WHERE status IN ('todo', 'in_progress')
            ) AS open,
            count(*) FILTER (
                WHERE status IN ('todo', 'in_progress')
                  AND due_at IS NOT NULL AND due_at < :now
            ) AS overdue,
            count(*) FILTER (
                WHERE status IN ('todo', 'in_progress')
                  AND due_at IS NOT NULL
                  AND due_at >= :start_of_day AND due_at < :end_of_day
            ) AS due_today,
            count(*) FILTER (
                WHERE status = 'completed'
                  AND completed_at IS NOT NULL AND completed_at >= :since_30d
            ) AS completed_30d
        FROM tasks
        WHERE organization_id = :org_id
    ),
    spend_stats AS (
        SELECT coalesce(sum(cost_usd), 0) AS spend_30d
        FROM provider_usage
        WHERE organization_id = :org_id AND usage_date >= :since_30d
    ),
    recent_activity AS (
        SELECT coalesce(
            jsonb_agg(
                jsonb_build_object(
                    'id', id,
                    'organization_id', organization_id,
                    'user_id', user_id,
                    'lead_id', lead_id,
                    'event_type', event_type::text,
                    'entity_type', entity_type,
                    'entity_id', entity_id,
                    'description', description,
                    'metadata', metadata,
                    'occurred_at', occurred_at,
                    'created_at', created_at
                ) ORDER BY occurred_at DESC, id DESC
            ),
            '[]'::jsonb
        ) AS items
        FROM (
            SELECT id, organization_id, user_id, lead_id, event_type,
                   entity_type, entity_id, description, metadata,
                   occurred_at, created_at
            FROM activity_logs
            WHERE organization_id = :org_id
            ORDER BY occurred_at DESC, id DESC
            LIMIT 10
        ) recent
    )
    SELECT
        lead_funnel.new, lead_funnel.researching, lead_funnel.contacted,
        lead_funnel.meeting_booked, lead_funnel.proposal_sent,
        lead_funnel.won, lead_funnel.lost,
        lead_extra.open_deals, lead_extra.unassigned_leads,
        won_stats.won_deals, won_stats.won_revenue,
        user_stats.total AS users_total, user_stats.active AS users_active,
        conversation_stats.open AS conversations_open,
        outreach_stats.outstanding AS outreach_outstanding,
        import_stats.active AS imports_active,
        task_stats.open AS tasks_open,
        task_stats.overdue AS tasks_overdue,
        task_stats.due_today AS tasks_due_today,
        task_stats.completed_30d AS tasks_completed_30d,
        spend_stats.spend_30d,
        recent_activity.items AS activity_items
    FROM lead_funnel
    CROSS JOIN lead_extra, won_stats, user_stats, conversation_stats,
        outreach_stats, import_stats, task_stats, spend_stats, recent_activity
    """
)

_FUNNEL_COLUMNS = (
    "new",
    "researching",
    "contacted",
    "meeting_booked",
    "proposal_sent",
    "won",
    "lost",
)


class DashboardRepository:
    """Data access for the dashboard landing-page snapshot."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def summary_snapshot(
        self,
        organization_id: uuid.UUID,
        *,
        now: datetime,
        start_of_day: datetime,
        end_of_day: datetime,
        since_30d: date,
    ) -> dict[str, Any]:
        """Return every dashboard counter in one round trip.

        Mirrors the predicates of the individual repository methods this
        replaces so the snapshot matches the old multi-query result exactly.
        """
        params = {
            "org_id": organization_id,
            "now": now,
            "start_of_day": start_of_day,
            "end_of_day": end_of_day,
            "since_30d": since_30d,
        }
        result = await self._session.execute(_SUMMARY_SQL, params)
        row = result.mappings().one()

        activity: list[dict[str, Any]] = list(row["activity_items"])

        return {
            "funnel": {
                column: int(row[column]) for column in _FUNNEL_COLUMNS
            },
            "users": {
                "total": int(row["users_total"]),
                "active": int(row["users_active"]),
            },
            "conversations": {"open": int(row["conversations_open"])},
            "outreach": {"outstanding": int(row["outreach_outstanding"])},
            "imports": {"active": int(row["imports_active"])},
            "tasks": {
                "open": int(row["tasks_open"]),
                "overdue": int(row["tasks_overdue"]),
                "due_today": int(row["tasks_due_today"]),
                "completed_30d": int(row["tasks_completed_30d"]),
            },
            "pipeline": {
                "won_deals": int(row["won_deals"]),
                "open_deals": int(row["open_deals"]),
                "won_revenue": float(row["won_revenue"]),
                "unassigned_leads": int(row["unassigned_leads"]),
            },
            "spend_30d": float(row["spend_30d"]),
            "recent_activity": activity,
        }
