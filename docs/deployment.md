# Deployment Guide

## Environments

| Variable              | Dev           | Staging         | Production          |
| --------------------- | ------------- | --------------- | ------------------- |
| `APP_ENV`             | development   | staging         | production          |
| `APP_DEBUG`           | `true`        | `false`         | `false`             |
| Database              | Docker Postgres | Docker Postgres | Managed Supabase  |
| `SUPABASE_URL`        | —             | staging project | production project  |
| `NEXT_PUBLIC_API_URL` | localhost     | staging URL     | production URL      |
| CORS origins          | localhost     | staging domains | production domains  |
| `OTEL_ENABLED`        | `false`       | `true`          | `true`              |

Create per-environment env files from the templates:

```bash
cp .env.example .env.production
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local
```

## Local / staging compose

```bash
docker compose up -d postgres n8n            # infrastructure only
docker compose --profile full up -d          # + backend + frontend (dev images)
docker compose logs -f
docker compose down
```

## Production compose (`docker-compose.prod.yml`)

Self-hosted reference deployment using multi-stage, non-root images with
container healthchecks (backend liveness probe + frontend HTTP check) so
orchestrators can restart unhealthy units:

```bash
cp .env.example .env.production   # fill in every value
make prod-build                   # builds from docker/*/Dockerfile.prod
make prod-up
```

Before pointing real traffic at it:

1. Terminate TLS at a reverse proxy in front of `backend:8000` / `frontend:3000`.
2. Prefer **managed Supabase** over the bundled `postgres` service; if
   self-hosting Postgres, enable backups (PITR) and strong credentials. See
   [Operations → Backup & Recovery](operations/backup-recovery.md) for the
   backup/restore runbook and RPO/RTO targets.
3. Pin `N8N_IMAGE_TAG` and set a strong, unique `N8N_ENCRYPTION_KEY` (replace
   the template placeholder — it is not fail-closed against weak values);
   keep n8n private (VPN/IP allow-list).
4. Set production `SECRET_KEY`, `CORS_ORIGINS`, `TRUSTED_HOSTS`, rate-limit
   values, and OTLP endpoint in `.env.production`.
5. Apply migrations (`make migrate`) and seeds before deploying new code.

### Networking & secret scoping

`docker-compose.prod.yml` now segments the stack onto two networks:

- **`dbnet`** (`internal: true`) — only `postgres`. `backend` and `worker`
  join it to reach the database; it is unreachable from `frontend` and `n8n`.
- **`appnet`** (bridge) — `backend`, `worker`, `frontend`, and `n8n`.
  `backend`/`worker` reach n8n's webhook here for dispatch.

The `n8n` container deliberately **no longer loads the whole `.env.production`**
(`env_file`) — it receives only its own `N8N_*` variables, so DB/SMTP/LLM/
credential secrets are not copied into the automation host. n8n persists to its
own SQLite volume (`n8ndata`) and does not use, or reach, Postgres.

## CI/CD

The pipeline (`.github/workflows/ci.yml`) runs on every push/PR:

1. **Backend:** `ruff check .` + `mypy app` + `pytest`
2. **Frontend:** `prettier --check` + `eslint` + `tsc --noEmit` + `vitest`
3. **Compose:** validates both `docker-compose.yml` and `docker-compose.prod.yml`

Deploy steps to add in your CD stage (after CI passes):

1. `docker compose -f docker-compose.prod.yml --env-file .env.production build`
2. Push images to a registry tagged with the commit/`APP_VERSION`.
3. Migrate + seed on the target environment.
4. Roll out services; import/upgrade n8n workflows; smoke-test `/health/ready`.

## Rollback

- Images are immutable and tagged; redeploy the previous tag to roll back.
- Database migrations are append-only — prefer additive changes and a forward
  repair migration over destructive `downgrade()` in production.
