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
| CSP (restrictive, on by default) | `backend/app/core/csp.py` (builder + startup validation)           |
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
| Credential envelope encryption | `backend/app/services/credential_crypto_service.py` (per-org DEKs + key rotation) |
| Automation kill switch         | `backend/app/services/automation_control_service.py` — operator-only global pause/resume |
| Fail-closed worker gate        | `backend/app/workers/execution_worker.py` — a settings outage pauses, never half-runs |
| No secrets in git              | `.gitignore` + `*.env.example` only                                  |

## Must-dos before production

1. **Secrets:** store `SECRET_KEY`, `N8N_ENCRYPTION_KEY`, Supabase service-role
   key, SMTP/API keys in a secret manager; inject as env vars at deploy time.
2. **TLS:** terminate HTTPS at a reverse proxy. CSP is on by default
   (`default-src 'self'` + hardening directives); only widen `connect-src` via
   `CSP_CONNECT_ORIGINS` for origins the UI actually reaches. Production config
   validation refuses to boot with `ENABLE_CSP=false`.
3. **CORS/trusted hosts:** set the real production origins and host headers.
4. **Rate limits:** choose per-endpoint limits based on expected traffic;
   connect Redis for multi-instance enforcement.
5. **AuthN/AuthZ:** implement authentication on top of `app/core/security.py`
   with short-lived access tokens + refresh rotation, and enforce RLS on every
   new table.
6. **Dependencies:** pin versions in production (incl. `N8N_IMAGE_TAG`) and
   run dependency scanning (e.g. `pip-audit`, `npm audit`) in CI.

## Automation kill switch

`GET/POST /api/v1/automation/status|pause|resume` is an operational emergency
control, not a tenant feature. It is gated to **admin** roles (`owner`/`admin`)
via the dedicated `AUTOMATION_CONTROL` permission (`app/core/permissions.py`),
and both toggles are written to the `activity_logs` audit trail with the acting
operator and reason. While paused, every automation entry point (queue, retry,
schedule dispatch, event publish, worker phases) fails closed with
`409 automation.paused…`, so a paused system cannot drift into partial
execution. The worker treats a settings read failure as paused (fail-closed)
rather than risk an unguarded run.

Treat the kill switch like a circuit breaker: use it during deploys/incidents
(see `docs/operations/admin-guide.md`) and keep the audit log reviewable. It
stops *new* automation; it does not kill in-flight executions (they complete or
time out normally) — if a hard stop is required, terminate the execution worker
processes first.

## Incident reporting

Use the request ID from error responses/logs when filing issues. Structured
logs already carry `request_id`; keep it when reporting to the team.
