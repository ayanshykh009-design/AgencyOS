# Database — Supabase (PostgreSQL)

The permanent source of truth for the AgencyOS data model. The backend mirrors
this schema locally for development and migrations.

## Folder layout

| Path                  | Purpose                                                        |
| --------------------- | -------------------------------------------------------------- |
| `schema/`             | Table-by-table SQL DDL (reference mirrors).                    |
| `migrations/`         | Versioned SQL migrations, applied in numeric order.            |
| `migrations/enums/`   | Canonical enum type definitions.                               |
| `seeds/`              | Idempotent bootstrap data (dev org, user, sources, leads).     |
| `supabase/`           | Supabase project config: `config.toml`, edge functions, policies. |
| `supabase/functions/` | Supabase Edge Functions (Deno), e.g. webhook receivers.        |
| `supabase/policies/`  | Row Level Security (RLS) policies per table.                   |

## Conventions

- **RLS first.** Every tenant-scoped table enables RLS in its migration and
  ships policies in `supabase/policies/`.
- **Migrations are append-only.** Never edit an applied migration; add a new
  numbered file.
- **Backend mirrors schema.** When a table changes, update
  `backend/app/models/` and `backend/app/schemas/` to match.
- **No secrets.** No credentials are stored in the schema — auth lives in
  Supabase Auth; provider keys in env vars.

## Tools

- Apply SQL migrations: `make migrate-sql` (idempotent, tracks versions in
  `public.schema_migrations`).
- Apply seeds: `make seed`.
- Local dev Postgres: the `postgres` service in `docker-compose.yml`.
- Supabase CLI (optional): `supabase start` from `supabase/config.toml`.

Full schema guide: `docs/database.md` · ERD: `docs/diagrams/database-erd.md`.
