# Deployment Guide

## Docker Compose

Local/staging deployments run the stack defined in `docker-compose.yml`:

```bash
docker compose --profile full up -d    # postgres + n8n + backend + frontend
docker compose logs -f                 # watch logs
docker compose down                    # stop
```

Configuration comes from the root `.env` file — provide real values in CI/CD.

## Environment matrix

| Variable                    | Dev      | Staging          | Production           |
| --------------------------- | -------- | ---------------- | -------------------- |
| `APP_ENV`                   | development | staging       | production           |
| `APP_DEBUG`                 | `true`   | `false`          | `false`              |
| Database                    | Docker Postgres | Docker Postgres | Managed Supabase |
| `SUPABASE_URL`              | —        | staging project  | production project   |
| `NEXT_PUBLIC_API_URL`       | localhost | staging URL     | production URL       |
| CORS origins                | localhost | staging domains  | production domain(s) |

## Production notes

- Serve frontend/backend behind TLS; terminate at a reverse proxy (nginx / LB).
- Use managed Supabase (not the Docker Postgres) with RLS enforced.
- Restrict n8n: VPN-only or IP-allowlisted; rotate `N8N_ENCRYPTION_KEY`.
- Rotate `SECRET_KEY` and Supabase keys per environment; never reuse dev keys.
- Back up Supabase (PITR) and `storage/` artifacts on a schedule.

## CI/CD

Pipeline steps (GitHub Actions example placeholder — see `.github/workflows/`):

1. `make lint`
2. `make test`
3. `docker compose build`
4. Migrate + seed on the target environment.
5. Deploy backend + frontend; import n8n workflows.
