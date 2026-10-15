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
| Revocable access tokens        | `users.token_version` + `tv` claim, enforced in `backend/app/api/deps.py`; bumped by auth-service logout/password change |
| Per-account login throttle     | `backend/app/services/auth_service.py` — progressive lock on *incorrect* passwords only (429 + `Retry-After`); a correct password always authenticates |
| Timing-safe login              | `verify_password_dummy()` in `backend/app/core/security.py` (unknown account costs the same as a real check) |
| Refresh-on-401 (client)        | `frontend/src/lib/api-client.ts` — single deduped refresh, then one retry |
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

## Auth session hardening

Stateless JWTs alone cannot be revoked before `exp`. The session layer closes
that gap and hardens the login surface:

- **Revocable access tokens.** Every JWT carries a `tv` claim mirroring
  `users.token_version`; `get_current_user` rejects any token whose `tv` is
  stale. Logout and password change bump the counter (and revoke all refresh
  tokens), so a leaked access token dies immediately.
- **Victim-safe brute-force throttle.** Failed logins increment
  `users.failed_login_attempts` and apply a progressive `locked_until`; only
  *incorrect* passwords are throttled (429 + `Retry-After`). A correct password
  always authenticates and clears the counter, so an attacker cannot lock a
  legitimate user out.
- **Timing-safe failure.** Unknown accounts run `verify_password_dummy()` so
  account existence is not leaked by response time.
- **Tenant-scoped FK checks.** Client-supplied `workflow_id` / `owner_user_id` /
  `lead_source_id` references are validated against the caller's organization
  (a bare FK only proves existence), preventing cross-tenant attachment.
- **Auth audit logging.** `agencyos.auth` logs login success/failure (email
  digest, not address), logout, and password change.
- **Refresh-token reuse detection.** Refresh tokens are opaque, rotated on
  every use, and grouped into a `family_id`. Presenting an already-rotated
  token is treated as theft: the whole family is revoked and the user's
  `token_version` is bumped, killing every outstanding access token
  (`auth.refresh_token_reuse`).

## Account security (email verification, password reset, TOTP MFA)

These flows ship disabled-by-default where behavior changes (email
verification, MFA) and are gated by env flags; production validation refuses
to boot if a mail-dependent feature is enabled without SMTP.

- **Email verification** (`EMAIL_VERIFICATION_ENABLED`). New accounts must
  confirm their email before login succeeds (`403 auth.email_verification_required`);
  existing rows are grandfathered. Tokens are single-use, SHA-256-hashed at
  rest (`auth_tokens`), short-lived, and delivered by email.
- **Password reset** (`PASSWORD_RESET_ENABLED`, default on). Enumeration-safe:
  the request endpoint always returns `202` whether or not the account exists
  (and burns comparable CPU for unknown addresses). Completing a reset revokes
  every existing session (`token_version` bump + refresh revocation).
- **TOTP two-factor** (`MFA_ENABLED`). Opt-in per account, two-step enrollment
  (pending secret → confirm a code → recovery codes issued once, Argon2-hashed).
  The login challenge is a short-lived JWT carrying `scope: "mfa"` that the
  auth guard rejects as an access token. Failed codes are throttled with a
  progressive lockout (`Retry-After`). TOTP secrets are encrypted at rest
  (`app/core/mfa.py`) and never returned by an API schema.

See `docs/api/endpoints/auth.md` for the endpoints and error codes.

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
