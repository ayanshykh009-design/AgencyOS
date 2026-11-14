# AgencyOS — Environment and Secrets Readiness

## Configuration sources

- Backend: `backend/app/core/config.py` (pydantic settings) + `backend/.env.example`.
- Frontend: `frontend/src/lib/env.ts` (zod) + `frontend/.env.example`.
- Compose: root `docker-compose.yml` (not modified here).

## Findings

### Documentation
- `backend/.env.example` documents every backend setting with inline guidance, including production-required values (`WORKER_DATABASE_URL`, `REDIS_URL`, `CREDENTIALS_ENC_KEY`, SMTP, etc.).
- `frontend/.env.example` documents the 4 public variables (`NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_APP_ENV`, Supabase public/anon).
- No committed `.env` / `.env.local` files found in the tracked tree (verified via `git ls-files`).

### Validation / fail-closed behavior
- `settings.validate_runtime()` and `validate_for_production()` are invoked in the app lifespan; production refuses to start on an owner/superuser DSN (`app/core/db_roles.py`).
- `REDIS_URL` is required outside development/test environments for shared rate limiting and resend cooldown; the default backend fails closed in staging/production (covered by `test_resend_cooldown.py`).
- `AI_ORG_DAILY_*_BUDGET=0` means "not configured" and fails closed (no AI execution).
- Feature flags default OFF (fail closed): `AGENT_RUNTIME_ENABLED`, `AI_MEMORY_ENABLED`, `COMMUNICATION_LAYER_ENABLED`, `GROWTH_AGENT_ENABLED`, `DELIVERY_ENABLED`, `FOUNDER_ASSISTANT_ENABLED`, `INTELLIGENCE_TRIAGE_ENABLED`, `EMAIL_VERIFICATION_ENABLED`, `CREDENTIAL_REKEY_ENABLED`.

### Secret handling
- Secrets (`SECRET_KEY`, `CREDENTIALS_ENC_KEY`, provider API keys, SMTP password, Supabase service-role key) are env-only; no values found committed (secret scan of tracked files: no matches for high-entropy committed credentials).
- Only `NEXT_PUBLIC_*` variables reach the browser bundle; backend secrets are server-side.
- Credentials at rest are envelope-encrypted with a versioned master key (`CREDENTIALS_ENC_KEY`, `CREDENTIAL_KEY_VERSION`), with dual-read rotation support.

### CORS / cookies / hosts
- `CORS_ORIGINS` defaults to `http://localhost:3000`; `TRUSTED_HOSTS` defaults to `localhost,127.0.0.1`; both must be overridden for deployment.
- Refresh cookie attributes are environment-aware (secure in production) — covered by `test_refresh_cookie.py`.
- `EMAIL_VERIFICATION_ENABLED=false` and `PASSWORD_RESET_ENABLED=true` by default; production SMTP is required when either is enabled.

### Deployment readiness risks (owner action)
- `APP_ENV` must be set to `production` (or staging) in deployed environments; defaults to `development`.
- `WORKER_DATABASE_URL` should be set to a `agencyos_worker`-member role for RLS to be meaningful; empty reuses `DATABASE_URL` (dev only).
- `REDIS_URL` must be set for multi-instance rate limiting.
- `CREDENTIALS_ENC_KEY` must be generated and stored in a secret manager.
- `SECRET_KEY` must be replaced with a long random value.

### Verdict
No known critical unsafe default that silently enables a feature in production. All high-risk toggles default OFF or fail closed. Configuration documentation is complete. Remaining items are owner-operated secret provisioning, not code defects.
