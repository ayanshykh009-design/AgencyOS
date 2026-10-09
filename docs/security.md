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
| Backend RLS (tenant isolation) | `database/migrations/0033_tenant_isolation_rls.sql` + `backend/app/core/tenant_context.py` |
| Restricted connection roles    | `agencyos_app` (RLS-enforced) via `DATABASE_URL`, `agencyos_worker` (BYPASSRLS) via `WORKER_DATABASE_URL` |
| Non-root prod containers       | `docker/*/Dockerfile.prod`                                           |
| No secrets in git              | `.gitignore` + `*.env.example` only                                  |
| Credential envelope encryption | `backend/app/services/credential_crypto_service.py` (per-org DEKs + key rotation) |
| Automation kill switch         | `backend/app/services/automation_control_service.py` — operator-only global pause/resume |
| Fail-closed worker gate        | `backend/app/workers/execution_worker.py` — a settings outage pauses, never half-runs |
| No secrets in git              | `.gitignore` + `*.env.example` only                                  |

## Tenant isolation (B-3)

No organization may read, mutate, or infer another organization's data. The
backend enforces this in three independent layers — defeating any single one
does not open a cross-tenant path:

1. **API/RBAC** — authenticated principal + permission checks
   (`backend/app/api/deps.py`, `backend/app/core/permissions.py`).
2. **Service/repository org scoping** — every query carries the current
   organization's predicate; repositories never accept a caller-supplied
   organization id without validating it against the session's tenant.
3. **PostgreSQL RLS** (`0033_tenant_isolation_rls.sql`) — policies
   `TO agencyos_app` scope every tenant table by
   `organization_id = public.tenant_org_id()`; cross-tenant writes fail with
   SQLSTATE 42501 even if a query in layers 1–2 is missed.

**Tenant GUC threat model.** `app.current_organization_id` is a custom
session GUC, set only by trusted server code: it is derived from the
verified JWT (`get_current_user` → `activate_org`), never from request
input, and re-applied from the request context on every transaction begin
so pooled connections cannot leak a previous request's tenant. No endpoint
accepts a GUC value — clients have no path to set it over HTTP; the
backend binds it server-side with `set_config(..., false)`.

**Connection roles.** `agencyos_app` and `agencyos_worker` (both NOLOGIN)
are the policy anchors; production traffic must connect as a LOGIN role
that is a **member** of `agencyos_app` via `DATABASE_URL`, and workers as a
member of `agencyos_worker` via `WORKER_DATABASE_URL` (required in
production config validation; workers are BYPASSRLS by design). Owner or
superuser DSNs bypass RLS entirely (no `FORCE ROW LEVEL SECURITY`) — that is
safe for dev/CI only; the shipped `docker-compose.prod.yml` therefore
carries an explicit operator note. Bootstrap (`docs/database.md`):

```sql
CREATE ROLE agencyos_api LOGIN PASSWORD '<strong-password>';
GRANT agencyos_app TO agencyos_api;
```

SECURITY DEFINER auth lookups (`app_get_user_by_email`, …) are revoked from
`PUBLIC` and granted only to the two anchor roles.

Behavioral proof lives in
`backend/tests/integration/test_tenant_isolation_rls.py` (PostgreSQL-gated,
runs in CI); static contract checks in
`backend/tests/integration/test_rls_policy_coverage.py`.

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
