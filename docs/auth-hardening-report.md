# AgencyOS — Authentication & Account Security Hardening Report

**Verdict: GO**
Commit `9886dfa` on `main` — CI green on the exact SHA (5/5 jobs):
<https://github.com/ayanshykh009-design/AgencyOS/actions/runs/38786143487>

## Scope

Four audit areas hardened with minimum justified fixes plus regression tests,
without regressing the existing architecture (layered backend, multi-tenancy,
RBAC, RLS, roadmap).

## Findings → fixes

| Area | Finding | Fix |
| ---- | ------- | --- |
| A — sessions/tokens/cookies | Refresh tokens rotate without reuse detection; no server-side access-token revocation; cookie flags incomplete | Migration 0035: token families + reuse detection (replay ⇒ family revocation + `token_version` bump); `tv` claim enforced in `app/api/deps.py`; logout/password-change revoke all sessions; `Secure` cookie flag; frontend refresh-on-401 |
| B — authz / IDOR | Client-supplied `workflow_id` / `owner_user_id` / `lead_source_id` accepted across tenants | Tenant-scoped FK validation in `lead_service`, `workflow_trigger_service`, `agent_service` |
| C — email verification + TOTP MFA | No email verification, no second factor | Migrations 0036/0037: hashed single-use `auth_tokens` + RLS, users verification/MFA columns, `user_recovery_codes` + RLS. `AccountSecurityService`, `MfaService` (TOTP secrets encrypted at rest, recovery codes Argon2-hashed). 8 new API endpoints |
| D — login/reset abuse protection | Login brute-force, password-reset enumeration, unthrottled flows | Victim-safe per-account login throttle (only *wrong* passwords; `429` + `Retry-After`), timing-safe failures, enumeration-safe password reset (always `202`), `RATE_LIMIT_STRICT` on all new endpoints, production boot fails if a mail flow is enabled without SMTP |

Feature flags default safe: `EMAIL_VERIFICATION_ENABLED=false`,
`MFA_ENABLED=false`, `PASSWORD_RESET_ENABLED=true`. Existing users are
grandfathered for email verification — nobody is retroactively locked out. The
MFA login challenge is a short-lived JWT carrying `scope: "mfa"` that the auth
guard rejects as an access token.

## Verification

| Gate | Result |
| ---- | ------ |
| Backend `ruff check app tests` | ✅ clean |
| Backend `mypy app` | ✅ 351 files, no issues |
| Backend `pytest` | ✅ exit 0 — **1553 passed, 77 skipped** (all skips = "PostgreSQL server not reachable") |
| Frontend format / lint / typecheck | ✅ / ✅ (0 errors, 1 pre-existing warning) / ✅ |
| Frontend tests | ✅ 148 passed (25 files) |
| `contract_diff.py` / `docs_api_consistency.py` | ✅ warnings only (by design for unwired routes) |
| `docs/api/openapi.yaml` | ✅ surgical splice only — 14 auth paths, all `$ref`s resolve (no wholesale regen) |
| Migration SHA pins | ✅ 0035/0036/0037 pinned; `test_all_migrations_immutable_sha256` green |
| CI @ `9886dfa` | ✅ all jobs incl. Postgres backend suite, contract/docs consistency, dependency scans, compose validation |

## Explicit non-blockers

1. **77 PG/RLS tests skipped locally** (no Docker/5432 on the dev machine) —
   they ran and passed in the CI Postgres job; skipped tests are never counted
   as passing.
2. **1 pre-existing frontend lint warning** (`postcss.config.mjs`, anonymous
   default export) — pre-dates this work.
3. **Feature flags off by default** — email verification and MFA require
   explicit opt-in; production config validation refuses to boot if a
   mail-dependent feature is enabled without `SMTP_HOST`/`SMTP_FROM_EMAIL`.
4. **Unrelated local notes left untracked**: `.opencode/plans/m8-founder-ai-assistant.md`
   and `.opencode/plans/m11-ai-brain-architecture.md` (preserved, not part of
   this change).

## Surface shipped

Migrations 0034–0037 (SHA-pinned, additive), backend services/repos/schemas,
8 new auth endpoints (`verify-email`, `verify-email/resend`,
`password-reset/request`, `password-reset/confirm`, `mfa/enroll`,
`mfa/activate`, `mfa/disable`, `mfa/verify`), 23 new backend tests, 5 new
frontend pages (verify-email, forgot-password, reset-password, MFA challenge,
settings → security), and updated docs (`openapi.yaml`,
`docs/api/endpoints/auth.md`, `docs/security.md`,
`docs/phase4.5-security-audit.md`, `backend/.env.example`, schema mirrors).

Full endpoint and error-code reference: [`docs/api/endpoints/auth.md`](api/endpoints/auth.md).
Control details: [`docs/security.md`](security.md#account-security-email-verification-password-reset-totp-mfa).
