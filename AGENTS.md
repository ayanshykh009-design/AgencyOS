# AGENTS.md — guidance for AI coding agents working in this repo

This file helps AI agents (and humans) understand how the repository is
organized and how to make changes that fit its conventions.

## Golden rules

1. **Skeleton first, logic later.** This is a scaffold repo. Keep changes
   aligned with the declared architecture instead of inventing new layouts.
2. **Layered backend.** Route handlers must stay thin. Flow:
   `app/api/v1/endpoints/*.py` (HTTP) → `app/services/*.py` (business logic) →
   `app/repositories/*.py` (data access) → `app/models/*.py` (ORM).
3. **DB lives in `database/`.** Schema, migrations, seeds, edge functions, and
   RLS policies belong there — the backend mirrors them locally.
4. **Prompts are versioned.** Every prompt in `prompts/` carries a name, version,
   status, and target model in its front-matter.
5. **No secrets in code.** All configuration flows through env vars
   (`*.env.example` templates only) and `app/core/config.py`.

## Where things live

| Concern            | Location                                |
| ------------------ | --------------------------------------- |
| HTTP API           | `backend/app/api/v1/endpoints/`         |
| Business logic     | `backend/app/services/`                 |
| Data access        | `backend/app/repositories/`             |
| DB migrations      | `backend/alembic/versions/`             |
| UI pages/routes    | `frontend/src/app/`                     |
| Shared UI          | `frontend/src/components/`              |
| n8n automation     | `workflows/n8n/workflows/`              |
| Prompt templates   | `prompts/<channel>/`                    |
| Docs               | `docs/`                                 |

## Commands

- Backend dev: `make backend` (or `uvicorn app.main:app --reload` in `backend/`)
- Frontend dev: `make frontend` (or `npm run dev` in `frontend/`)
- Infra: `make up` / `make down`
- Backend tests: `make test`
- Lint: `make lint`
- Migrations: `make migrate`
