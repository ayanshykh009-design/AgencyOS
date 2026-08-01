# AGENTS.md — guidance for AI coding agents working in this repo

This file helps AI agents (and humans) understand how the repository is
organized and how to make changes that fit its conventions.

## Golden rules

1. **Production discipline.** This project targets a commercial SaaS with
   thousands of users. Never build quick prototypes: every addition ships with
   tests, lint-clean code, proper error handling, and updated docs.
2. **Layered backend.** Route handlers must stay thin. Flow:
   `app/api/v1/endpoints/*.py` (HTTP) → `app/services/*.py` (business logic) →
   `app/repositories/*.py` (data access) → `app/models/*.py` (ORM).
3. **DB lives in `database/`.** Schema, migrations, seeds, edge functions, and
   RLS policies belong there — the backend mirrors them locally.
4. **Prompts are versioned.** Every prompt in `prompts/` carries a name, version,
   status, and target model in its front-matter.
5. **No secrets in code.** All configuration flows through env vars
   (`*.env.example` templates only) and `app/core/config.py`.
6. **Consistent failure behavior.** Errors go through the unified envelope in
   `app/core/errors.py`; do not leak stack traces to clients.
7. **Don't regress hardening.** Keep request-ID/security middleware, rate
   limiting, structured logging, and prod config validation intact.

## Where things live

| Concern            | Location                                |
| ------------------ | --------------------------------------- |
| HTTP API           | `backend/app/api/v1/endpoints/`         |
| Business logic     | `backend/app/services/`                 |
| Data access        | `backend/app/repositories/`             |
| DB migrations      | `backend/alembic/versions/`             |
| Error handling     | `backend/app/core/{errors,exception_handlers}.py` |
| Middleware         | `backend/app/core/middleware.py`        |
| UI pages/routes    | `frontend/src/app/`                     |
| Shared UI          | `frontend/src/components/`              |
| Env validation (FE)| `frontend/src/lib/env.ts` (zod)         |
| n8n automation     | `workflows/n8n/workflows/`              |
| Prompt templates   | `prompts/<channel>/`                    |
| CI pipeline        | `.github/workflows/ci.yml`              |
| Prod Dockerfiles   | `docker/*/Dockerfile.prod`              |
| Docs               | `docs/`                                 |

## Commands

- Full local CI: `make ci` (lint + test for backend and frontend)
- Backend dev: `make backend` (or `uvicorn app.main:app --reload` in `backend/`)
- Frontend dev: `make frontend` (or `npm run dev` in `frontend/`)
- Infra: `make up` / `make down`
- Backend tests: `make test`
- Lint: `make lint`
- Migrations: `make migrate-sql` (V1 SQL schema) or `make migrate` (Alembic, experimental)
- Prod build: `make prod-build` (needs `.env.production`)

## Definition of done for any feature

1. Backend: schema → model → schema (Pydantic) → repository → service → thin endpoint.
2. Tests: `backend/tests/` (unit → integration → api) and/or frontend `*.test.ts(x)`.
3. `make ci` passes locally.
4. Docs updated (`docs/api/endpoints/`, etc.) in the same change.
