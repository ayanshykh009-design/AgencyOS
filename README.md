# AI Outreach Agency Operating System (AgencyOS)

A modular, production-grade monorepo for running an AI-powered outreach agency:
lead sourcing, AI personalization, multi-channel outreach (cold email, LinkedIn,
follow-ups), and campaign orchestration — all driven by reusable AI prompts and
automation workflows.

> **Status:** Foundational skeleton + V1 database foundation, engineered to
> production SaaS standards. The 15-core-table schema (SQL migrations, RLS
> policies, seeds, SQLAlchemy mirrors, Pydantic contracts, tests) is in place;
> no business features are implemented yet beyond the data layer.

---

## Monorepo Layout

| Path            | Purpose                                                                              |
| --------------- | ------------------------------------------------------------------------------------ |
| `backend/`      | Python + **FastAPI** REST API — the orchestration and business-logic layer.          |
| `frontend/`     | **Next.js + TypeScript** web app — agency dashboard and client-facing UI.            |
| `workflows/`    | **n8n** automation workflows — lead sourcing, enrichment, and pipeline automation.   |
| `database/`     | **Supabase (PostgreSQL)** schema, migrations, seeds, edge functions, RLS policies.   |
| `prompts/`      | Versioned **AI prompt library** — cold email, follow-ups, LinkedIn, personalization. |
| `docs/`         | Architecture, setup, security, observability, API, and deployment documentation.     |
| `scripts/`      | Development, DB, and deployment scripts.                                             |
| `docker/`       | Dev + multi-stage production Dockerfiles for every service.                          |
| `storage/`      | Local artifacts: uploads, exports, logs, backups (ignored by git).                   |
| `tests/`        | Cross-service and end-to-end test suites.                                            |

## Tech Stack

| Layer        | Technology                                                       |
| ------------ | ---------------------------------------------------------------- |
| Backend      | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy (async), Alembic   |
| Frontend     | Next.js (App Router), React, TypeScript, Tailwind, Vitest, zod   |
| Database     | Supabase (PostgreSQL 16) + RLS                                   |
| Automation   | n8n                                                              |
| AI           | Provider-agnostic prompt layer (OpenAI / Anthropic)              |
| Infra        | Docker Compose (dev + prod), multi-stage images, GitHub Actions  |

## Production-grade foundations (already in place)

- **Layered backend** (`router → service → repository`) with thin handlers.
- **V1 database foundation:** 15 core tables (orgs, users, leads, outreach,
  conversations, imports, provider usage) with SQL migrations, RLS, seeds,
  SQLAlchemy mirrors, Pydantic schemas, and tests — see `docs/database.md`.
- **Unified error envelope** and structured exceptions — no leaked internals.
- **Request IDs, security headers, Host allow-listing, and rate limiting.**
- **Structured JSON logs** (prod) and optional **OpenTelemetry** traces.
- **Fail-fast config validation** for `APP_ENV=production`.
- **Argon2id password hashing** and JWT with issuer/audience validation.
- **Non-root, multi-stage production images** (backend + Next.js standalone).
- **CI pipeline** (`.github/workflows/ci.yml`): lint, typecheck, tests, compose.
- **Production compose** (`docker-compose.prod.yml`) with healthchecks + limits.

## Quick Start

```bash
# 1. Clone the repo and enter it
cd AgencyOS

# 2. Copy environment templates (see docs/setup.md for details)
make setup            # or: scripts/setup/setup-dev.ps1  (Windows) / .sh (Unix)

# 3. Start infrastructure (Postgres + n8n by default)
make up

# 4. Apply SQL migrations + seeds (V1 schema)
make migrate-sql && make seed

# 5. Run the backend locally
make backend          # uvicorn on http://localhost:8000  (docs at /docs)

# 6. Run the frontend locally
make frontend         # Next.js on http://localhost:3000
```

Run the full local CI pipeline anytime: `make ci`.

See [docs/setup.md](docs/setup.md) for full instructions,
[docs/architecture.md](docs/architecture.md) for the system design, and
[docs/deployment.md](docs/deployment.md) for production deployment.

## Repository Conventions

- **Layered backend:** `router → service → repository`, no business logic in route handlers.
- **Versioned prompts:** every prompt has a name, version, status, and target model.
- **DB-first:** schema lives in `database/` (Supabase); the backend mirrors it locally.
- **No secrets:** anything sensitive lives in `.env` files, never committed.
- **Production discipline:** no prototype shortcuts — every addition must ship
  with tests, lint-clean code, and updated docs (see `AGENTS.md`).
