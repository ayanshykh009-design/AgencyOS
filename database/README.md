# Database — Supabase (PostgreSQL)

The source of truth for the AgencyOS data model. The backend mirrors this
schema locally for development and migrations.

## Folder layout

| Path                | Purpose                                                          |
| ------------------- | ---------------------------------------------------------------- |
| `schema/`           | Table-by-table SQL schema definitions (DDL source of truth).     |
| `migrations/`       | Versioned schema migrations (SQL), applied in order.             |
| `seeds/`            | Seed data scripts (roles, defaults, sample campaigns).           |
| `supabase/`         | Supabase project config: `config.toml`, edge functions, policies. |
| `supabase/functions/` | Supabase Edge Functions (Deno), e.g. webhook receivers.          |
| `supabase/policies/`  | Row Level Security (RLS) policies per table.                     |

## Conventions

- **RLS first.** Every table that stores tenant/agency data must have RLS
  policies defined here — the API never bypasses them in production.
- **Migrations are append-only.** Never edit an applied migration; add a new
  numbered file (e.g. `0002_add_sequences.sql`).
- **Backend mirrors schema.** When a table changes here, update
  `backend/app/models/` to match.

## Tooling

- Local dev uses the Postgres service in `docker-compose.yml`.
- Supabase CLI (optional): `supabase start` spins up the full local stack from
  `supabase/config.toml`.
- Apply seeds: `make seed` (see `scripts/db/seed.sh`).
