# Phase 4.5 — Production Deployment Checklist

Operational checklist for taking AgencyOS to production. Items marked ✅ are
already satisfied in the codebase; items marked ⬜ are operator actions that
must be performed at deploy time with real credentials/domains.

## Codebase State (verified during this audit)

| Control | Status | Where |
| ------- | ------ | ----- |
| Multi-stage, non-root prod images | ✅ | `docker/backend/Dockerfile.prod`, `docker/frontend/Dockerfile.prod` |
| Container healthchecks | ✅ | backend liveness probe + frontend HTTP check |
| Fail-fast prod config | ✅ | `Settings.validate_for_production()` in `backend/app/core/config.py` |
| Env templates only (no secrets) | ✅ | `.env.example` / `backend/.env.example` / `frontend/.env.example` |
| Frontend env validation | ✅ | `frontend/src/lib/env.ts` (zod, fails fast) |
| Security headers (FE + BE) | ✅ | `frontend/next.config.mjs` + `backend/app/core/middleware.py` |
| Request-ID tracing | ✅ | `backend/app/core/middleware.py` |
| Rate limiting | ✅ | `backend/app/core/rate_limit.py` (Redis for multi-instance) |
| Unified error envelope (no stack traces) | ✅ | `backend/app/core/errors.py` |
| Argon2id password hashing | ✅ | `backend/app/core/security.py` |
| JWT iss/aud validation | ✅ | `backend/app/core/security.py` |
| RBAC on all API endpoints | ✅ | `backend/app/core/permissions.py` + `require_permission` |
| RLS policies for tenant tables | ✅ | `database/supabase/policies/` |
| Append-only migration strategy | ✅ | `database/migrations/`, forward-repair policy |
| CI pipeline | ✅ | `.github/workflows/ci.yml` (ruff, mypy, pytest, prettier, eslint, tsc, vitest, compose validation) |

## Pre-Deploy Operator Checklist

### Secrets & Configuration
- ⬜ Store `SECRET_KEY` (32+ bytes), Supabase service-role key, SMTP keys, and
  LLM provider keys in a secret manager; inject as env vars at deploy time.
- ⬜ Set `APP_ENV=production`, `APP_DEBUG=false` in `.env.production`
  (backend fail-fast validation will reject violations).
- ⬜ Set `CORS_ORIGINS` and `TRUSTED_HOSTS` to the real production domains.
- ⬜ Pin `N8N_IMAGE_TAG` and rotate `N8N_ENCRYPTION_KEY`; keep n8n private
  (VPN / IP allow-list).
- ⬜ Set per-endpoint rate limits and connect Redis for multi-instance
  enforcement.

### Networking
- ⬜ Terminate TLS at a reverse proxy in front of `backend:8000` /
  `frontend:3000`.
- ⬜ Set `ENABLE_CSP=true` after validating the exact content policy against
  the UI (documented in `docs/security.md`).
- ⬜ Bake the real `NEXT_PUBLIC_API_URL` at frontend build time
  (`NEXT_PUBLIC_*` vars are not available at runtime in the standalone server).

### Database
- ⬜ Prefer managed Supabase over the bundled `postgres` service.
- ⬜ If self-hosting Postgres: enable backups (PITR) and strong credentials.
- ⬜ Apply migrations + seeds before deploying new code
  (`make migrate` / `make migrate-sql`).
- ⬜ Verify RLS is enabled on every tenant table
  (`database/supabase/policies/`).

### Observability
- ⬜ Set `OTEL_ENABLED=true` and the OTLP endpoint.
- ⬜ Wire log shipping (structured logs) and alerting on liveness/readiness
  failures, 429 rate-limit spikes, and auth-failure bursts
  (see `docs/observability.md`).

## Smoke Test (post-deploy)

1. `GET /api/v1/health/live` and `GET /api/v1/health/ready` → 200.
2. Register an org, log in, create a lead, move it through a pipeline stage,
   create a task + note, and confirm the dashboard summary reflects the data.
3. Create a team invite and confirm the returned `invite_url` renders the
   accept screen (the `/invite/[token]` page is a Phase 5 item — the backend
   `GET /api/v1/teams/public/{token}` + `POST /api/v1/teams/accept` flow is
   verified and tested).
4. Confirm a non-admin cannot reach `PATCH /api/v1/ai/settings` (403) and a
   viewer cannot call `POST /api/v1/ai/run` or `/ai/dispatch`.
5. Export a lead CSV and confirm row counts + sanitization.

## Rollback

- Images are immutable and tagged; redeploy the previous tag to roll back.
- Prefer a forward repair migration over destructive `downgrade()`.

## Conclusion

**Status: ✅ Codebase is deployment-ready.** Every control within the repo is
in place and verified. Remaining items are environment-specific operator
actions (secrets, TLS, domains, observability endpoints) that cannot be
validated without real infrastructure.
