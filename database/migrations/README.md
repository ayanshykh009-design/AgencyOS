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
