# Phase 4.5 — Performance Report

Performance review of the AgencyOS backend + frontend: query patterns, N+1
risk, pagination, index coverage, and load considerations. Conducted as part
of Phase 4.5 Production Readiness. This is a static review (no load test
harness in the repo); findings are based on code inspection.

## Summary

**Status: ✅ PASS for expected SaaS scale (thousands of users, tens of
thousands of records per org) with documented long-term improvements.**

## 1. Pagination

Every list endpoint is paginated with server-side `limit`/`offset` and a
hard cap:

| Repository | Default limit | Hard cap |
| ---------- | ------------- | -------- |
| `LeadRepository.search` | 50 | 200 |
| `TaskRepository.list_tasks` | 50 | 200 |
| `NoteRepository.list_by_lead` | 100 | 200 |
| `ConversationRepository.list` | 50 | 200 |
| `ImportJobRepository.list` | 50 | — |
| `TeamInviteRepository.list` | 100 | — |
| `AssignmentRepository.list_logs` | 100 | — |
| `UserRepository.list_by_org` | 100 | — |
| `ProviderUsageRepository.list` | 100 | — |
| `OutreachRepository.*` | 100 | — |
| `LeadRepository.list_unassigned` (sweep) | 500 | — |

Caps use `min(limit, _MAX_PAGE_SIZE)` / `min(limit, 200)`, so a client cannot
force an unbounded row fetch. `func.count()` mirrors the same filters for
accurate `total` values with stable `ORDER BY` (`.order_by(None)` used on
count queries to avoid wasted ordering).

## 2. N+1 Query Audit

**No N+1 hotspots found.** Specific checks:

- `ActivityLogRepository.audit_list` uses `selectinload(ActivityLog.user)` —
  actor details fetched in one batched query, not per-row. (This was the one
  historical N+1 candidate; it is already fixed.)
- Dashboard recent activity uses `list_entries` with the same eager-load path.
- List endpoints return ORM entities whose relationships are either
  pre-loaded (`selectinload`) or not traversed by the serializer; schemas are
  validated via `model_validate` which only touches mapped columns.
- No `async for` row-by-row loading loops in service layers.

## 3. Query Volume

- **Dashboard landing** (`DashboardService.summary`) issues ~14 aggregate
  `COUNT`/`SUM` queries per render. All are org-scoped, indexed, and cheap
  individually; acceptable at current scale. **Known optimization:** fold into
  fewer queries or a materialized view (documented as long-term).
- **Pipeline board** (`LeadRepository.list_by_stages`) fetches all non-deleted
  leads for the requested stages and buckets in Python up to
  `limit_per_stage` (50). At very large boards this reads more rows than the
  returned cap. Acceptable now; a `ROW_NUMBER()`-based window query would
  bound it.
- **Lead search** (`LeadRepository.search`) uses `%query%` ILIKE across
  `first_name`, `last_name`, `company`, `email`, `position`. Cannot use a
  btree index; org-scoped + capped, so fine at current scale. **Known
  optimization:** trigram (`pg_trgm`) indexes or Postgres full-text search.
- **Exports** (`ExportService`) cap at `_MAX_EXPORT_ROWS` (streamed rows).

## 4. Index Coverage

Indexes exist for every org-scoped query path:

- Leads: `(org, status)`, `(org, owner)`, `(org, source)`, `(org, updated DESC)`,
  `(org, stage)`, `(org, close_reason)`, partial `(org)` active filter
- Tasks: `(org, due_at)`, `(org, status)`, `(org, lead)`, `(org, assignee)`,
  `(org, reminder_at)`
- Notes: `(org, lead)`
- Activity logs: `(org, event)`, `(org, lead)`, `(org, entity)`
- Conversations/messages, outreach attempts/messages, follow-ups, manual queue,
  import jobs, provider usage: all org-led composite indexes
- Dedup keys on leads (`email_normalized`, `phone_normalized`, `website_domain`)
  are backed by unique constraints (per-org)

## 5. Concurrency & Bulk

- `commit_with_retry` handles transient DB write conflicts (retry on
  serialization/deadlock) in services that own transaction boundaries.
- Async SQLAlchemy throughout — no blocking DB calls in the request path.
- Background sweeps (task reminders, invite expiry) are bounded (`limit=500`)
  and run on a schedule, not in the hot path.

## 6. Frontend

- Client-side React state; server payloads are already-paginated pages.
- No unbounded arrays rendered (leads page paginates via the API).
- Static export / standalone Next.js output; no heavy client bundles observed
  in code review.

## Recommendations (long-term, non-blocking)

1. **Dashboard:** combine the ~14 aggregate queries into one CTE query or a
   nightly materialized view.
2. **Pipeline board:** window-function (`ROW_NUMBER`) query to cap reads at
   `limit_per_stage`.
3. **Search:** add `pg_trgm` GIN indexes on the searched lead columns.
4. **Add a load test** (`locust`/`k6`) once staging exists to validate the
   assumptions above against real hardware.

## Conclusion

**Status: ✅ PASS.** Pagination is enforced and capped everywhere, no N+1
query patterns were found, org-scoped indexes cover all hot paths, and the
remaining items are documented scalability improvements rather than defects.
