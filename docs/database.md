# Database Guide

AgencyOS uses **Supabase (PostgreSQL 16)** as the permanent source of truth.
This document describes the V1 schema, conventions, migration flow, and how
the backend mirrors it.

## Source of truth

| Concern            | Location                                             |
| ------------------ | ---------------------------------------------------- |
| SQL migrations     | `database/migrations/` (append-only, applied in order) |
| Enum types         | `database/migrations/enums/` (canonical reference)   |
| Per-table DDL      | `database/schema/` (readable mirrors of migrations)  |
| RLS policies       | `database/supabase/policies/`                        |
| Seeds              | `database/seeds/`                                    |
| ORM mirror         | `backend/app/models/` (SQLAlchemy)                   |
| API contracts      | `backend/app/schemas/` (Pydantic)                    |
| Enum mirror        | `backend/app/models/enums.py`                        |

When a table changes: update the migration + `schema/` mirror, then the ORM
model, the Pydantic schemas, and this doc in the same change.

## Conventions

- **Primary keys:** `UUID` (`gen_random_uuid()`), mirror `UUIDPrimaryKeyMixin`.
- **Audit columns:** every mutable table has `created_at` and `updated_at`
  (`TimestampMixin`); `updated_at` is maintained by the `set_updated_at()`
  trigger. Append-only tables (`conversation_messages`, `activity_logs`,
  `import_row_errors`) keep only `created_at`.
- **Soft delete:** `leads.deleted_at` (nullable) for tenant data; prefer soft
  delete over hard `DELETE` in the service layer.
- **Timestamps:** always `timestamptz`, stored UTC.
- **Naming:** `snake_case`; singular table names (`lead`, `user`), plural
  reserved for the physical tables where the plan names them so
  (`organizations`, `users`, `leads`, `follow_ups`, `conversations`).
- **No secrets in plaintext:** API keys/tokens never appear in plaintext
  columns. `credentials.encrypted_value` holds envelope-encrypted secrets
  (`v<key_version>:<base64(nonce || ct)>`, see `app/core/crypto.py`); other
  auth material lives in Supabase Auth and env vars (`app/core/config.py`).
- **Tenancy:** every tenant-scoped table has `organization_id` →
  `organizations(id)` with `ON DELETE CASCADE`; RLS scopes all access by it.

## Tables (V1)

| # | Table                  | Purpose                                   |
| - | ---------------------- | ----------------------------------------- |
| 1 | `organizations`        | Multi-tenant root (agency tenants)        |
| 2 | `users`                | Agency team members (role per org)        |
| 3 | `lead_sources`         | Labelled sources leads come from          |
| 4 | `leads`                | Prospects with org-scoped dedup           |
| 5 | `lead_research`        | AI/manual enrichment, one row per lead    |
| 6 | `outreach_messages`    | Reusable per-channel message templates    |
| 7 | `outreach_attempts`    | One send attempt with delivery tracking   |
| 8 | `follow_ups`           | Scheduled follow-ups in a sequence        |
| 9 | `manual_outreach_queue`| Human-triggered outreach tasks            |
| 10| `conversations`        | Reply threads with a lead                 |
| 11| `conversation_messages`| Append-only thread history                |
| 12| `activity_logs`        | Append-only business audit trail          |
| 13| `import_jobs`          | CSV import runs (import-only)             |
| 14| `import_row_errors`    | Per-row import failures                   |
| 15| `provider_usage`       | Daily provider token/request accounting   |
| 16| `team_invites`         | Team invitation lifecycle                 |
| 17| `lead_assignment_rules`| Round-robin / strategy assignment rules   |
| 18| `lead_assignment_logs` | Immutable assignment-change trail         |
| 19| `pipeline_stages`      | Sales pipeline stages (position-ordered)  |
| 20| `close_reasons`        | Won/lost close reason taxonomy            |
| 21| `tasks`                | Team tasks (lead-linked, due/reminder)    |
| 22| `notes`                | Free-form notes per lead/org              |
| 23| `workflows`            | Automation definitions (`active`/`paused`/`archived`) |
| 24| `workflow_triggers`    | Manual / event / schedule trigger definitions (`schedule_cron`, `last_fired_at`) |
| 25| `workflow_executions`  | Execution queue + state machine (`attempts`, `next_retry_at`, `cancel_requested_at`, `idempotency_key`) |
| 26| `workflow_events`      | Published domain events (event-driven triggers) |
| 27| `execution_events`     | Append-only per-attempt execution timeline (technical) |
| 28| `worker_health`        | Worker instance heartbeats (liveness)     |
| 29| `system_settings`      | Operator key/value settings (automation kill switch) |
| 30| `credentials`          | Envelope-encrypted org secrets            |
| 31| `credential_key_versions` | Key-rotation ledger                     |

See the ERD in [diagrams/database-erd.md](diagrams/database-erd.md).

## Enum types

Defined in `database/migrations/enums/` and materialized by `0001_core_enums.sql`:

| Enum                  | Values                                                                        |
| --------------------- | ----------------------------------------------------------------------------- |
| `user_role`           | `owner`, `admin`, `member`, `viewer`                                          |
| `lead_status`         | `new`, `researching`, `contacted`, `meeting_booked`, `proposal_sent`, `won`, `lost` |
| `outreach_channel`    | `email`, `whatsapp`, `contact_form`, `linkedin`, `instagram`, `facebook`       |
| `outreach_status`     | `queued`, `sending`, `sent`, `delivered`, `failed`, `skipped`, `manually_sent`, `replied` |
| `import_status`       | `pending`, `processing`, `completed`, `failed`, `cancelled`                   |
| `activity_event_type` | `lead_imported`, `research_completed`, `score_generated`, `email_sent`, `whatsapp_sent`, `manual_message_completed`, `reply_received`, `meeting_booked`, `proposal_sent`, `lead_won`, `lead_lost`, `execution_queued`, `execution_started`, `execution_completed`, `execution_failed`, `execution_retried`, `execution_cancelled`, `workflow_activated`, `workflow_paused`, `workflow_archived`, `automation_paused`, `automation_resumed` |
| `conversation_sender` | `lead`, `agent`, `system`                                                     |
| `execution_event_type` | `queued`, `started`, `adapter_dispatched`, `adapter_returned`, `step_started`, `step_completed`, `step_failed`, `retrying`, `succeeded`, `failed`, `cancelled`, `timed_out`, `timeout_guard` |

The backend mirrors every enum in `backend/app/models/enums.py`. Never rename
or reorder values after release; add new ones via `ALTER TYPE ... ADD VALUE`.

## Duplicate protection (leads)

Normalized dedup keys are **generated columns**, so normalization is enforced
by the database:

| Column              | Generated from                           | Example                       |
| ------------------- | ---------------------------------------- | ----------------------------- |
| `email_normalized`  | `lower(btrim(email))`                    | `ADA@X.com` → `ada@x.com`     |
| `phone_normalized`  | digits of `phone` or `whatsapp` (whichever is present) | `+44 (20)` → `4420` |
| `website_domain`    | host of `website`, no `www.`, lowercased  | `https://www.X.com/a` → `x.com` |

Org-scoped **partial unique indexes** (NULL-tolerant) are the duplicate
protection:

- `uq_leads_org_email` on `(organization_id, email_normalized)`
- `uq_leads_org_phone` on `(organization_id, phone_normalized)` — phone and
  WhatsApp share one uniqueness bucket
- `uq_leads_org_website_domain` on `(organization_id, website_domain)`

Import pipelines write the raw values; the database computes the normalized
keys and rejects duplicates.

## Row Level Security (RLS)

Every tenant-scoped table:

1. Enables RLS in its migration (`ALTER TABLE ... ENABLE ROW LEVEL SECURITY`).
2. Has policy files in `database/supabase/policies/` applied in the
   Supabase-managed environment.
3. Policy helper `public.tenant_org_id()` resolves the caller's organization
   from `auth.uid()`.

`anon` and `authenticated` are Supabase roles; policy files require them.

## Migrations

| Scope                | Tool                      | Location                          |
| -------------------- | ------------------------- | --------------------------------- |
| Supabase / prod      | SQL migrations            | `database/migrations/`            |
| Local dev            | SQL migrations (psql)     | `scripts/db/migrate.sh`           |
| Alembic (optional)   | Alembic                   | `backend/alembic/versions/`       |

SQL migrations are the schema source of truth. `scripts/db/migrate.sh`
applies them in numeric order and records applied versions in
`public.schema_migrations` (idempotent). Alembic remains available for local
experimentation but is not the V1 schema path.

Run SQL migrations: `make migrate-sql` (or `scripts/db/migrate.sh`).

## Seeds

Idempotent, fixed-UUID seed data in `database/seeds/`. `01_core_seed.sql`
bootstraps one dev organization, one owner user, three lead sources, and two
sample leads. Run via `make seed` (or `scripts/db/seed.sh`).

## Testing

- Unit tests (`backend/tests/unit/`) validate enum sets, ORM metadata
  (UUID PKs, FKs, partial unique indexes, computed columns, relationships),
  and Pydantic validation — no database required.
- Integration tests (`backend/tests/integration/test_database_schema.py`)
  apply the migrations to a disposable PostgreSQL database and verify
  duplicate protection, enum rejection, check constraints, cascades, the
  `updated_at` trigger, and generated columns. They auto-skip when no server
  is reachable (`TEST_POSTGRES_URL` to point at one).
