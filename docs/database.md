# Database Guide

## Source of truth

The schema lives in `database/` (SQL DDL + migrations). The backend mirrors
tables in `backend/app/models/` (SQLAlchemy) for local dev and complex queries;
Alembic migrations live in `backend/alembic/`.

## Conventions

- **Primary keys:** `UUID` (`uuid_generate_v4()` / Python `uuid4`).
- **Audit columns:** every table gets `created_at` and `updated_at`
  (`TimestampMixin` / SQL default `now()`).
- **Soft delete:** prefer a `deleted_at` column over hard `DELETE` for
  tenant-data tables.
- **Timestamps:** always `timestamptz`, store UTC.
- **Naming:** `snake_case` for columns/tables; singular table names
  (`users`, `campaigns`, `prospects`).

## Row Level Security (RLS)

Every tenant-scoped table must:

1. Enable RLS: `ALTER TABLE ... ENABLE ROW LEVEL SECURITY;`
2. Define policies in `database/supabase/policies/`.
3. Set service-role access via the backend ONLY where RLS isn't sufficient.

## Migrations

| Scope          | Tool                     | Location                         |
| -------------- | ------------------------ | -------------------------------- |
| Supabase prod  | SQL migrations           | `database/migrations/`           |
| Local dev      | Alembic                  | `backend/alembic/versions/`      |

Keep both in sync when a table changes (or standardize on one source per table).

## Seeds

Idempotent seed scripts in `database/seeds/`, run via `make seed`.
