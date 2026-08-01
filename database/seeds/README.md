# Seeds

Deterministic, idempotent bootstrap data. Fixed UUIDs make every statement
re-runnable (`ON CONFLICT DO NOTHING`).

- `01_core_seed.sql` — dev organization, dev owner user, three lead sources,
  two sample leads.

Run via `make seed` (or `scripts/db/seed.sh`). Migrations must be applied
first (`make migrate-sql`).

Seeds are for local/dev bootstrapping only — never point them at production.
PostgreSQL is the permanent source of truth; CSV files are import-only and
are never overwritten by the database.
