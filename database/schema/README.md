# Schema definitions

Table-by-table SQL DDL mirroring `../migrations/` (which is the versioned
source of truth). One `.sql` file per table plus shared helpers:

- `_helpers.sql` — `set_updated_at()` trigger and the normalize functions.
- `00_enums.sql` — reference copy of every enum type.
- `organizations.sql`, `users.sql`, `lead_sources.sql`, `leads.sql`,
  `lead_research.sql`, `outreach_messages.sql`, `outreach_attempts.sql`,
  `follow_ups.sql`, `manual_outreach_queue.sql`, `conversations.sql`,
  `conversation_messages.sql`, `activity_logs.sql`, `import_jobs.sql`,
  `import_row_errors.sql`, `provider_usage.sql`.

These files use `IF NOT EXISTS` so they are safe to run as reference DDL.
When a table changes:

1. add a migration in `../migrations/`,
2. update the matching `schema/*.sql` file,
3. mirror the change in `../../backend/app/models/` and `../../backend/app/schemas/`.
