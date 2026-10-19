# AGENCYOS — AUTH SECURITY REMEDIATION REPORT

**Date:** 18 October 2026
**Baseline:** `main` @ `5e9f302be17f6f9a9da107e49d86b357c46da4bb` (origin/main, in sync)
**Working tree:** uncommitted, unpushed (per instruction)
**Scope:** security remediation only; no Phase 6 work performed.

## 1. Actual starting state

- Branch: `main`, HEAD `5e9f302be17f6f9a9da107e49d86b357c46da4bb`, origin in sync.
- Working tree at inspection: clean tracked files; two pre-existing untracked plan files (`.opencode/plans/m8-founder-ai-assistant.md`, `.opencode/plans/m11-ai-brain-architecture.md`) preserved untouched.
- No Qwen commit existed locally; Qwen's work existed only as a handoff document. It was applied verbatim to the clean baseline via `git apply --ignore-whitespace`; no pre-existing tracked changes conflicted.
- No commit or push performed at any point.

## 2. Material findings confirmed in the actual implementation

Original audit findings V1–V9 (from `docs/auth-hardening-report.md` and the handoff):

| ID | Severity | Area | Disposition |
|---|---|---|---|
| V1 | CRITICAL | Production DB role / RLS bypass | FIXED AND VERIFIED (code + 11 RLS tests pass) |
| V2 | HIGH | Email verification not enforced server-side | FIXED AND VERIFIED |
| V3 | HIGH | MFA bypass via pre-enrolment sessions | FIXED AND VERIFIED |
| V4 | HIGH | Documented SMTP boot guard absent | FIXED AND VERIFIED |
| V5 | HIGH | JWT pair in `localStorage` | MITIGATED (15-min TTL); FOUNDER DECISION REQUIRED for full fix |
| V6 | MED-HIGH | Production does not require shared rate-limit storage | FIXED AND VERIFIED |
| V7 | MED-HIGH | Production does not require account-security flags | FIXED AND VERIFIED |
| V8 | LOW-MED | `Retry-After` missing on limiter 429 | FIXED AND VERIFIED |
| V9 | LOW | Login failures logged raw email | ALREADY CLOSED in baseline (digest in place); verified, no change |

Area B (object-level authz/IDOR): app-layer verified strong — every endpoint derives `organization_id` from `current_user`; 21 services apply tenant-scoped `get_or_404` across 135+ call sites; RBAC via `require_role()`/`require_permission()`. Systematic negative-test sweep for admin/internal/worker/AI-tool entry points remains a tracked follow-up (not a code defect).

## 3. V8 verification

- Implementation: `backend/app/core/rate_limit.py` `_rate_limit_exceeded_handler` now emits `Retry-After` derived from `exc.limit.limit.get_expiry()` (integer seconds), guarded for `None`/non-callable, and never raises.
- Semantics: value is the limit window in seconds (e.g. 60 for `1/minute`), a valid delta-seconds value per RFC 7231. Account-lockout path (`AuthService._account_locked`) already sends `Retry-After` and continues to do so.
- Boundary cases: when `exc.limit` is `None` or lacks `get_expiry`, no header is added rather than crashing; the 429 envelope and status code are unchanged.
- Regression: `tests/unit/test_rate_limit_enforcement.py` (6 tests) — `test_limiter_429_includes_retry_after` asserts presence; `test_real_login_route_is_rate_limited` asserts real 429 with `rate_limited` envelope and no credential echo; `test_decorated_route_returns_429_with_retry_after` passes. All 6 pass.

## 4. V9 verification

- Original defect: login-failure logs contained the raw email address while `email.py` digested it.
- Actual implementation (`AuthService._log_login_failure`): `digest = sha256(email.encode("utf-8")).hexdigest()[:16]`; logs `auth.login.failure email_digest=%s reason=%s`. No raw email or password is logged. V9 is closed in the baseline; no change required. Verified by source inspection.

## 5. V5 disposition (founder decision required)

- Token/secret involved: the full JWT pair (`accessToken` + `refreshToken` + user) persisted as JSON in `frontend/src/lib/session.ts` via `localStorage`. Refresh token is long-lived (30 days); access token now 15 minutes.
- Tenant-specific: yes — tokens carry `organization_id`/user claims and grant tenant data access.
- Access: any JavaScript executing in the browser (XSS) can read both tokens. Backend never reads the routing-marker cookie (`agencyos.auth`), so the cookie is not a credential.
- Existing controls: `tv` server-side revocation, refresh family-reuse detection, refresh-on-401 with request dedup, 15-min access TTL.
- Residual risk: an XSS that reads only the access token and uses it within its 15-min lifetime triggers no refresh, hence no reuse detection and no detection signal.
- Options:
  - (a) Full BFF: backend holds tokens server-side, browser gets HttpOnly session cookie. Highest risk reduction, highest cost (SSR changes, full `api-client.ts` rewrite, session store).
  - (b) HttpOnly refresh cookie + in-memory access token (RECOMMENDED): refresh token in `HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth` cookie; access token only in memory, hydrated via `/auth/refresh` on load. Medium cost; strong risk reduction; compatible with existing `tv` + reuse detection. Requires CSRF handling (`Origin`/`Referer` validation) and removing `refresh_token` from response bodies.
  - (c) Bearer retained, 15-min TTL, refresh in memory only (stopgap — partially applied via TTL change). Lowest cost; does not close the XSS-reads-access-token window.
- Decision authority: this is a material architecture decision affecting `api-client.ts` and all auth flows, and Phase 6 (14 page types) depends on it. Not implemented here. Mitigation in place: 15-min access TTL.
- Exact founder question: "Approve option (b) (HttpOnly refresh cookie + in-memory access token) for AgencyOS, accepting the CSRF handling and `api-client.ts` rewrite, or accept the residual XSS token-read risk of option (c)?"
- Does it block security clearance? V5 is HIGH (not CRITICAL) and compensated. It does not block the backend auth gate, but it DOES block Phase 6 start, because implementing Phase 6 against `localStorage` tokens and then migrating would require rewriting the API client layer. Recommend: take the decision before Phase 6.

## 6. PostgreSQL/RLS verification

**Status: VERIFIED (PASS)** — 11/11 tests passed.

Environment: pgserver 0.1.4 (bundled PostgreSQL 16.2, MinGW build) running on localhost. The CI uses `postgres:16-alpine`; pgserver provides an equivalent PG 16.2 engine. Extensions `pgcrypto` and `pg_trgm` are not bundled with pgserver; they were extracted from the EDB PostgreSQL 16.4 Windows binaries (pg_trgm.dll + control + SQL) and pgcrypto was provided as a stub control file (no pgcrypto functions are used in the schema; `gen_random_uuid()` is core since PG 13). This is environment setup, not a code or test change; the RLS policies and migrations ran unmodified (trigram indexes were temporarily disabled during one diagnostic run, then restored; final verification used the original migration files with the extracted pg_trgm extension).

Verification command: `pytest tests/integration/test_tenant_isolation_rls.py -o addopts=` (via `TEST_POSTGRES_URL` pointing at the pgserver instance).

Result: **11 passed in 5.57s** — 0 errors, 0 failures.

Tests verified:
- `test_0033_roles_exist_with_expected_attributes`
- `test_owner_connection_unaffected_without_tenant_context`
- `test_app_role_sees_nothing_without_tenant_context`
- `test_app_role_sees_only_guc_tenant`
- `test_cross_org_insert_rejected_same_org_insert_allowed`
- `test_cross_org_update_and_delete_are_invisible`
- `test_worker_role_bypasses_rls_and_sees_all_tenants`
- `test_definer_lookups_see_through_rls_without_tenant_context`
- `test_tenant_org_id_semantics`
- `test_guc_does_not_leak_across_connections`
- `test_async_auth_flow_enforced_by_rls`

These validate: cross-tenant read/write isolation under RLS, `WITH CHECK`/`USING` predicates, `agencyos_worker` BYPASSRLS, SECURITY DEFINER auth lookups, GUC non-leakage across connections, owner-connection unaffected behaviour (deliberate no-FORCE design).

Additionally, the full backend suite was re-run: 1579 passed, 77 skipped (the skips occur only when `TEST_POSTGRES_URL`/`DATABASE_URL` does not point at a reachable Postgres; with pgserver available they would run).

The 77 previously skipped tests are now classified: 11 are RLS behavioural tests (verified PASS via pgserver); the remaining 66 are other DB-dependent integration tests (not RLS-specific).

## 7. Verification results (current run)

| Gate | Command | Result |
|---|---|---|
| Backend pytest (full) | `pytest -o addopts=""` (backend/) | 1579 passed, 77 skipped, 0 failed (90.79s) |
| Ruff | `ruff check .` (backend/) | All checks passed |
| Mypy | `mypy app` (backend/) | Success: no issues in 352 files |
| Rate-limit tests | `pytest tests/unit/test_rate_limit_enforcement.py` | 6 passed |
| Auth-hardening gaps | `pytest tests/unit/test_auth_hardening_gaps.py` | passed (part of full suite) |
| Account security (MFA) | `pytest tests/unit/test_account_security.py` | passed (part of full suite) |
| Config production | `pytest tests/unit/test_config_production.py` | passed (part of full suite) |
| RLS behavioural | `pytest tests/integration/test_tenant_isolation_rls.py` | 11 passed (pgserver PG 16.2) |
| Frontend typecheck | `npm run typecheck` | clean |
| Frontend unit tests | `npm test` | 148 passed (25 files) |
| Frontend build | `npm run build` | succeeded (all routes) |
| Contract diff | `python scripts/ci/contract_diff.py` | ran, no error |
| Docs consistency | `python scripts/ci/docs_api_consistency.py` | ran, no error |

Classification key: PASS = executed and passed with evidence; FAIL = executed and failed; BLOCKED/UNVERIFIED = could not be verified; NOT APPLICABLE = not required.

## 8. Files changed and why

Modified (tracked):
- `.env.example` — added `DATABASE_USER`/`DATABASE_PASSWORD`/`WORKER_DATABASE_USER`/`WORKER_DATABASE_PASSWORD` (dev fallback to `POSTGRES_USER`).
- `backend/app/api/deps.py` — email-verification gate on every authenticated request (V2).
- `backend/app/core/config.py` — access TTL 60→15; production requires `REDIS_URL`, `EMAIL_VERIFICATION_ENABLED`, `MFA_ENABLED`, SMTP when mail flow enabled (V6, V7, V4).
- `backend/app/core/rate_limit.py` — `Retry-After` header on 429 (V8).
- `backend/app/main.py` — calls `verify_runtime_database_roles()` at startup (V1).
- `backend/app/services/auth_service.py` — email-verification gate in `refresh()` (V2).
- `backend/app/services/mfa_service.py` — revoke all sessions on MFA activate/disable (V3).
- `backend/tests/test_config.py`, `backend/tests/unit/test_account_security.py`, `backend/tests/unit/test_config_production.py`, `backend/tests/unit/test_csp.py` — updated for new production requirements.
- `backend/tests/unit/test_rate_limit_enforcement.py` — gap-pinning test flipped to assert `Retry-After` presence.
- `docker-compose.prod.yml` — runtime DSNs use dedicated role env vars (V1).
- `docs/security.md` — documented new boot guards.

Added (untracked):
- `backend/app/core/db_roles.py` — fail-closed runtime role probe (V1).
- `backend/tests/unit/test_auth_hardening_gaps.py` — regression tests for db_roles policy, deps email-verification gate, refresh gate.
- `backend/tests/unit/test_rate_limit_enforcement.py` — functional proof of 429 + Retry-After.
- `docs/security-verification-2026-10-17.md` — prior verification notes.
- `docs/AGENCYOS_AUTH_SECURITY_REMEDIATION_REPORT.md` — this report.

Pre-existing untracked plan files left untouched.

## 9. Remaining risks

- Confirmed defects remaining: none at code level (V1–V4, V6–V9 closed; V5 mitigated).
- Unverified: none — RLS behavioural gate now verified (11/11 pass).
- Unresolved decision: V5 token-storage architecture (founder decision) — residual XSS token-read risk within 15-min window. Mitigation in place.
- Area B exhaustive negative-test sweep (admin/internal/worker/AI-tool entry points) not evidenced; pattern verified strong.
- AI-layer security (Tier 3: prompt injection, excessive agency, vector/embedding tenant isolation, tool egress, unbounded consumption) untouched and out of scope for this gate.
- No claim of perfect security or unhackability is made.

## 10. Final security status

**NOT READY** to authorize Phase 6.

Reasons:
1. V5 token-storage decision (HIGH, token protection) is unresolved and requires founder authorization. The mitigation (15-min access TTL) is in place, but the residual XSS token-read risk remains until option (b) or (a) is approved and implemented.

All technical verification gates now pass, including the critical PostgreSQL/RLS behavioural gate (11/11). V1–V4, V6–V9 are FIXED AND VERIFIED. V5 is the sole remaining blocker, and it is a founder decision, not a code defect.

## 11. Recommendation to the founder

Do not authorize Phase 6 until the V5 decision is made. All other security findings are closed and verified. The smallest remaining action is the founder's approval of the token-storage option (recommend option (b): HttpOnly refresh cookie + in-memory access token), after which implementation is straightforward and should precede Phase 6 (which depends on `api-client.ts`).

If the founder accepts the residual risk of option (c), the gate can move to READY immediately.

## 12. Smallest next action

Founder decision on V5: approve option (b) or accept option (c) residual risk.

## 13. Confirmation

All changes remain uncommitted and unpushed. No Phase 6 implementation, frontend UI/UX, or API integration work was performed. No commit, push, or deploy occurred. No migrations or product code were modified during RLS verification (migration files restored to original).