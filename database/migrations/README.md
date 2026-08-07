# Migrations

Versioned, append-only SQL schema migrations — the source of truth for the
AgencyOS schema. Naming: `NNNN_description.sql` (e.g. `0001_core_enums.sql`).

| Migration                 | Contents                                             |
| ------------------------- | ---------------------------------------------------- |
| `0001_core_enums.sql`     | All `ENUM` types (see `enums/` for the reference)    |
| `0002_tenant_identity.sql`| `organizations`, `users`, `set_updated_at()` trigger |
| `0003_lead_tables.sql`    | `lead_sources`, `leads` (dedup), `lead_research`     |
| `0004_outreach_tables.sql`| `outreach_messages`, `outreach_attempts`, `follow_ups`, `manual_outreach_queue` |
| `0005_conversations_activity.sql` | `conversations`, `conversation_messages`, `activity_logs` |
| `0006_imports_provider.sql` | `import_jobs`, `import_row_errors`, `provider_usage` |
| `0007_auth.sql`             | `users.password_hash`, `refresh_tokens` (rotation-based) |
| `0008_team_management.sql`  | `user_role` grows `manager`/`sales_agent`, `team_invites` |
| `0009_lead_assignment.sql`  | `lead_assignment_rules`, `lead_assignment_logs` (immutable), `assignment_method`/`assignment_strategy` enums |
| `0010_pipeline_management.sql` | `pipeline_stages`, `close_reasons`, `stage_lifecycle` enum, lead stage/deal columns |
| `0011_tasks.sql`            | `tasks`, `task_status`/`task_priority`/`recurrence_frequency` enums, task activity events |
| `0012_notes.sql`            | `notes`, note activity events |
| `0013_automation.sql`       | `workflows`, `workflow_triggers`, `workflow_executions`, `workflow_events`, `credentials`, automation enums + activity events |
| `0014_schedule_last_fired.sql` | `workflow_triggers.last_fired_at` + partial schedule-due index |
| `0015_credential_key_versions.sql` | `credential_key_versions`, `credentials.key_version`/`last_rotated_at`, partial unique per-version index |
| `0016_search_trigram_indexes.sql` | `pg_trgm` GIN indexes for leading-wildcard lead/task search |
| `0017_automation_hardening.sql` | `execution_event_type` enum, `execution_events` (append-only timeline), `worker_health` (heartbeats), `system_settings` (kill switch), `workflow_executions` hardening columns (`cancel_requested_at`, `cancelled_by_user_id`, `idempotency_key` + indexes), `automation_paused`/`automation_resumed` activity events |

Rules:

- One migration per file, applied in ascending numeric order.
- Each migration is reversible on paper (rollback comment at the bottom).
- Never edit an applied migration — add a new one instead.
- `enums/` holds the canonical enum definitions; keep `0001` in sync with it.
- `schema/` mirrors the DDL per table for readability; keep it in sync too.

Apply locally: `make migrate-sql` (or `scripts/db/migrate.sh`). Applied
versions are tracked in `public.schema_migrations`, so re-runs are a no-op.

> Alembic (`backend/alembic/`) still exists for local experimentation but the
> SQL migrations are the V1 schema path; keep the two in sync if both are used.
