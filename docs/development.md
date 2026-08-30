# Development Guide

## Workflow

1. Branch per feature from `main`: `git checkout -b feat/<name>`.
2. Implement following the layered conventions (see `AGENTS.md`).
3. Run quality gates before commit — they mirror CI:

```bash
make ci       # ruff + eslint + prettier + tsc + pytest + vitest
# or individually:
make lint
make test
make format   # auto-fix ruff + prettier
```

> **`make ci` requires PostgreSQL.** The integration + e2e suites delete/skip
> when no server is reachable, so `make ci` now runs a `pgcheck` guard that
> aborts (instead of a false-green skip) if PostgreSQL is not running. Start
> it with `make up`/`docker compose up -d postgres` (or point
> `TEST_POSTGRES_URL` at an existing server) before `make ci`. Override only
> for frontend-only runs with `make ci SKIP_DB_GUARD=1`.

4. Open a PR with a concise description; update related docs in the same PR.

## Conventions

- **Commits:** imperative, scoped, e.g. `feat(auth): add login endpoint`.
- **API changes:** bump `app/api/v1` only — breaking changes go into a new
  versioned router.
- **Prompt changes:** never edit an `active` prompt — add `name@version` and
  update consumers.
- **Secrets:** only `.env.example` templates are committed; never `.env`.
- **Errors:** raise `AppError` (see `backend/app/core/errors.py`) instead of
  returning ad-hoc error shapes.
- **Frontend env:** validate new `NEXT_PUBLIC_*` vars in `src/lib/env.ts` (zod)
  rather than reading `process.env` inline.

## Running subsets

```bash
cd backend && pytest tests/api          # only API tests
cd frontend && npm run lint -- src/lib  # eslint on a path
cd frontend && npm test                 # vitest
cd frontend && npm run format           # prettier write
```

## Adding a feature end-to-end

1. Schema + migration + RLS policies → `database/`.
2. ORM model + Alembic migration → `backend/app/models/`, `backend/alembic/`.
3. Schemas (Pydantic) → `backend/app/schemas/`.
4. Repository → `backend/app/repositories/`.
5. Service → `backend/app/services/`.
6. Endpoints → `backend/app/api/v1/endpoints/` (thin, `AppError` on failures).
7. Tests → `backend/tests/` (unit → integration → api).
8. Frontend service + page → `frontend/src/services/`, `frontend/src/app/`.
9. Update docs → `docs/api/endpoints/` and the relevant guides.

## Frontend structure

Pages live under `frontend/src/app/(dashboard)/` and always route data through
`frontend/src/services/*` (never raw `fetch`). Each page renders loading,
error, and empty states and uses the primitives in `frontend/src/components/ui/`.

| Page | Route | Purpose |
| ---- | ----- | ------- |
| Dashboard | `/dashboard` | Metrics incl. tasks + deal-flow widgets |
| Leads | `/leads`, `/leads/[id]` | List/filter/export, profile, notes, tasks |
| Pipeline | `/pipeline` | Kanban board with drag-and-drop stage moves |
| Tasks | `/tasks` | Filterable task list with create/complete/delete |
| Search | `/search` | Unified search across leads, tasks, notes |
| Audit log | `/audit` | Admin-only activity trail (owner/admin) |
| Team | `/team` | Invites, roles, member activation (owner/admin) |
| Assignment | `/assignment` | Auto-assignment rules + unassigned sweep |

UI affordances are gated with `can()` from `frontend/src/lib/permissions.ts`,
which mirrors the backend permission matrix; the backend remains the source of
truth for enforcement. New pages must add matching service modules with vitest
coverage under `frontend/src/services/__tests__/`.

## Production discipline

- Use the production Dockerfiles (`docker/*/Dockerfile.prod`) to validate that
  new dependencies build cleanly and images remain non-root.
- Keep `docker-compose.prod.yml` and `.github/workflows/ci.yml` in sync with
  any new service or quality gate you add.
