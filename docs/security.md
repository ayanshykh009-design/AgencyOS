# Security Guide

Security is layered and enforced by default. This page documents the controls
that are wired into the foundation — treat them as a contract, not a suggestion.

## Principles

- **Defense in depth:** transport (TLS) → application (middleware, authz) →
  data (RLS) → secrets (env/secret manager).
- **Fail closed:** invalid config, tokens, or requests produce safe failures,
  never partial/leaky behavior.
- **Least privilege:** service-role keys stay server-side; the browser only
  ever sees anon keys + RLS.

## Controls already implemented

| Control                        | Where                                                               |
| ------------------------------ | ------------------------------------------------------------------- |
| Request-ID tracing             | `backend/app/core/middleware.py` (echoed on every response)         |
| Security headers               | `backend/app/core/middleware.py` + `frontend/next.config.mjs`       |
| Host allow-listing             | `TrustedHostMiddleware` via `TRUSTED_HOSTS`                          |
| CORS allow-list                | `CORS_ORIGINS` (never `*` with credentials)                          |
| Rate limiting                  | `backend/app/core/rate_limit.py` (Redis for multi-instance)          |
| Unified error envelope         | `backend/app/core/errors.py` — no stack traces to clients            |
| Argon2id password hashing      | `backend/app/core/security.py` (pwdlib)                              |
| JWT with iss/aud validation    | `backend/app/core/security.py` (PyJWT)                               |
| Fail-fast prod config          | `Settings.validate_for_production()` in `backend/app/core/config.py` |
| RLS-first data access          | `database/supabase/policies/` (required for every tenant table)      |
| Non-root prod containers       | `docker/*/Dockerfile.prod`                                           |
| No secrets in git              | `.gitignore` + `*.env.example` only                                  |

## Must-dos before production

1. **Secrets:** store `SECRET_KEY`, `N8N_ENCRYPTION_KEY`, Supabase service-role
   key, SMTP/API keys in a secret manager; inject as env vars at deploy time.
2. **TLS:** terminate HTTPS at a reverse proxy; set `ENABLE_CSP=true` once the
   exact content policy is validated against the UI.
3. **CORS/trusted hosts:** set the real production origins and host headers.
4. **Rate limits:** choose per-endpoint limits based on expected traffic;
   connect Redis for multi-instance enforcement.
5. **AuthN/AuthZ:** implement authentication on top of `app/core/security.py`
   with short-lived access tokens + refresh rotation, and enforce RLS on every
   new table.
6. **Dependencies:** pin versions in production (incl. `N8N_IMAGE_TAG`) and
   run dependency scanning (e.g. `pip-audit`, `npm audit`) in CI.

## Incident reporting

Use the request ID from error responses/logs when filing issues. Structured
logs already carry `request_id`; keep it when reporting to the team.
