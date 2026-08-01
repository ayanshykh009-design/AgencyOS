# AgencyOS Backend — Python + FastAPI

REST API and orchestration layer for the AI Outreach Agency Operating System.

## Architecture (layered)

Requests flow through strictly separated layers — keep it that way:

```
HTTP Router (app/api/v1/endpoints/)  ->  Service (app/services/)
     ->  Repository (app/repositories/)  ->  Models (app/models/) / Supabase
```

| Folder          | Responsibility                                                    |
| --------------- | ----------------------------------------------------------------- |
| `app/api/`      | HTTP layer: routers, FastAPI dependencies (`deps.py`), v1 API.    |
| `app/core/`     | Cross-cutting concerns: config, logging, security, database.      |
| `app/models/`   | SQLAlchemy ORM models (mirror of the `database/` schema).         |
| `app/schemas/`  | Pydantic v2 request/response schemas (API contract).              |
| `app/services/` | Business logic — intentionally empty until features are built.    |
| `app/repositories/` | Data access — the only place that talks to the persistence layer. |
| `app/workers/`  | Background jobs / task queue hooks (Celery/RQ stubs).             |
| `alembic/`      | Alembic migration scripts.                                        |
| `tests/`        | Pytest suites (unit, integration, api).                           |

## Local development

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # or .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Interactive API docs: `http://localhost:8000/docs` (Swagger) and `/redoc`.

## Conventions

- **No business logic in routers** — delegate to services/repositories.
- **Settings only via env vars** (`app/core/config.py`), never hardcoded.
- **Version the API** under `app/api/v1/`; add `v2/` later, never break v1.
