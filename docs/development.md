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

## Production discipline

- Use the production Dockerfiles (`docker/*/Dockerfile.prod`) to validate that
  new dependencies build cleanly and images remain non-root.
- Keep `docker-compose.prod.yml` and `.github/workflows/ci.yml` in sync with
  any new service or quality gate you add.
