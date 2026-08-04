# Dashboard Analytics

Aggregate, org-scoped metrics for the landing page. All endpoints are
JWT-authenticated.

## GET /api/v1/dashboard/summary

Return the full snapshot in one call.

```json
{
  "leads": {"new": 3, "researching": 1, "contacted": 2, "meeting_booked": 0,
            "proposal_sent": 0, "won": 4, "lost": 1, "total": 11},
  "users": {"total": 8, "active": 7},
  "conversations": {"open": 2},
  "outreach": {"outstanding": 5},
  "imports": {"active": 1},
  "tasks": {"open": 6, "overdue": 2, "due_today": 1, "completed_30d": 14},
  "pipeline": {"won_deals": 4, "open_deals": 6, "won_revenue": 1250.5,
               "unassigned_leads": 2},
  "activity": {"recent": [/* last 10 activity entries */]},
  "usage": {"spend_last_30_days_usd": 12.34}
}
```

| Section      | Meaning                                                     |
| ------------ | ----------------------------------------------------------- |
| `leads`      | Counts per lifecycle status plus `total`                    |
| `users`      | Total and active members                                    |
| `conversations` | Open conversations                                       |
| `outreach`   | Outstanding outreach attempts                               |
| `imports`    | Active import jobs                                          |
| `tasks`      | Open, overdue, due-today, and completed-in-last-30-days tasks |
| `pipeline`   | Won/open deal counts, won revenue, unassigned leads         |
| `activity`   | Most recent 10 audit entries                                |
| `usage`      | LLM spend over the last 30 days (USD)                       |

The `tasks` and `pipeline` sections are additive (backward compatible): clients
that ignore unknown keys continue to work.

### Performance

The whole snapshot is computed by a single SQL statement
(`backend/app/repositories/dashboard.py`): all counters are folded into one
round trip via WITH (CTE) blocks over 8 tables, and the recent-activity feed is
collapsed into a JSON array inside the same query. The response shape is
unchanged from the previous multi-query implementation.

## Authentication

`Authorization: Bearer <token>`. Errors use the standard envelope.
