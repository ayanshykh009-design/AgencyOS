# AI Outreach Agency Operating System (AgencyOS)

A modular, enterprise-ready monorepo for running an AI-powered outreach agency:
lead sourcing, AI personalization, multi-channel outreach (cold email, LinkedIn,
follow-ups), and campaign orchestration — all driven by reusable AI prompts and
automation workflows.

> **Status:** Project skeleton only. No business logic is implemented yet.
> This repository defines the folder structure, conventions, and starter files
> that teams extend with real features.

---

## Monorepo Layout

| Path            | Purpose                                                                              |
| --------------- | ------------------------------------------------------------------------------------ |
| `backend/`      | Python + **FastAPI** REST API — the orchestration and business-logic layer.          |
| `frontend/`     | **Next.js + TypeScript** web app — agency dashboard and client-facing UI.            |
| `workflows/`    | **n8n** automation workflows — lead sourcing, enrichment, and pipeline automation.   |
| `database/`     | **Supabase (PostgreSQL)** schema, migrations, seeds, edge functions, RLS policies.   |
| `prompts/`      | Versioned **AI prompt library** — cold email, follow-ups, LinkedIn, personalization. |
| `docs/`         | Architecture, setup, API, and operational documentation.                             |
| `scripts/`      | Development, DB, and deployment scripts.                                             |
| `docker/`       | Dockerfiles and container configurations for every service.                          |
| `storage/`      | Local artifacts: uploads, exports, logs, backups (ignored by git).                   |
| `tests/`        | Cross-service and end-to-end test suites.                                            |

## Tech Stack

| Layer        | Technology                                             |
| ------------ | ------------------------------------------------------ |
| Backend      | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy (async)  |
| Frontend     | Next.js (App Router), React, TypeScript, Tailwind      |
| Database     | Supabase (PostgreSQL 16) + RLS                        |
| Automation   | n8n                                                   |
| AI           | Provider-agnostic prompt layer (OpenAI / Anthropic)   |
| Infra        | Docker Compose, Makefile                              |

## Quick Start

```bash
# 1. Clone the repo and enter it
cd AgencyOS

# 2. Copy environment templates (see docs/setup.md for details)
make setup            # or: scripts/setup/setup-dev.ps1  (Windows) / .sh (Unix)

# 3. Start infrastructure (Postgres + n8n by default)
make up

# 4. Run the backend locally
make backend          # uvicorn on http://localhost:8000  (docs at /docs)

# 5. Run the frontend locally
make frontend         # Next.js on http://localhost:3000
```

See [docs/setup.md](docs/setup.md) for full instructions and
[docs/architecture.md](docs/architecture.md) for the system design.

## Repository Conventions

- **Layered backend:** `router → service → repository`, no business logic in route handlers.
- **Versioned prompts:** every prompt has a name, version, status, and target model.
- **DB-first:** schema lives in `database/` (Supabase); the backend mirrors it locally.
- **No secrets:** anything sensitive lives in `.env` files, never committed.
