# AgencyOS — Unified Authentication Security Verification (17 October 2026)

Independent re-verification of the hardening landed in `9886dfa`, followed by a
scoped remediation pass. Audit-only until Stage 6; no unrelated refactoring.

## Baseline reproduced

| Gate | Result before any change |
| ---- | ------------------------ |
| Backend `pytest` | **1553 passed, 77 skipped** — identical to `docs/auth-hardening-report.md` |
| Skip reasons | all 77 = "PostgreSQL server not reachable" (no Docker/5432 here) |
| Frontend `vitest` | **148 passed (25 files)** |

HEAD at audit time: `5e9f302be17f6f9a9da107e49d86b357c46da4bb` on `main`.
CI run **#43** (`9886dfa`) and **#44** (`5e9f302`) both `completed/success`, 5/5 jobs.

## Confirmed gaps closed

| # | Gap | Fix |
| - | --- | --- |
| 1 | **Documented control did not exist.** `app/core/email.py` and `docs/auth-hardening-report.md` both claimed production boot fails when a mail flow is enabled without SMTP. `validate_for_production()` contained no such check. With `PASSWORD_RESET_ENABLED=true` (the default) and no SMTP, reset emails silently no-op behind a 202. | Guard added to `validate_for_production()`; the documentation claim is now true. |
| 2 | **Email verification was not enforced server-side.** `register()` mints a token pair in the same transaction as the account; `get_current_user()` and `refresh()` never checked `email_verification_required`, so an unverified user held a working session and could rotate it for the full refresh lifetime. Only a *fresh login* was gated. | Gate added to `app/api/deps.py` (403 `auth.email_verification_required`) and to `AuthService.refresh()`. Grandfathered accounts unaffected. |
| 3 | **MFA could be bypassed via pre-enrolment sessions.** `MfaService.activate()`/`disable()` changed the second factor without touching `token_version` or revoking refresh tokens, so a token minted before enrolment kept rotating for up to `REFRESH_TOKEN_EXPIRE_DAYS` without ever presenting the factor. | `_revoke_all_sessions()` added and called from both paths. |
| 4 | **Production could run with required protections disabled.** `EMAIL_VERIFICATION_ENABLED` and `MFA_ENABLED` default to `false`; nothing required them in production. | `validate_for_production()` now requires both. Enrolment stays per-user opt-in — no universal-MFA policy is imposed. |
| 5 | **RLS was not load-bearing in production.** Migration 0033 deliberately omits `FORCE ROW LEVEL SECURITY`, so isolation depends entirely on the connection role. `validate_for_production()` only checked the DSN *scheme*, and `docker-compose.prod.yml` wired **both** DSNs to `${POSTGRES_USER}` — the cluster owner/superuser. A default production deploy therefore bypassed every tenant policy while the green B-3 suite (which assumes the role via `SET ROLE`) kept passing. | New `app/core/db_roles.py`: startup probe refuses to boot in production on a superuser DSN or a role lacking `agencyos_app` / `agencyos_worker` membership. Compose now uses `DATABASE_USER` / `WORKER_DATABASE_USER` (dev fallback preserved). |

## Verified already-correct controls (left unchanged)

Argon2id hashing; timing-safe dummy verify for unknown accounts; victim-safe
progressive lockout (a correct password always authenticates); JWT `iss`/`aud`
pinned with an algorithm allowlist; `tv` claim enforced against
`users.token_version`; refresh rotation with family-reuse detection; opaque
high-entropy tokens hashed at rest; recovery codes Argon2-hashed and
single-use; TOTP secret encrypted at rest; MFA challenge token rejected as an
access token; `_dev_url()` returns `None` in production; password reset revokes
all sessions; **every endpoint derives `organization_id` from `current_user`**
(no client-supplied tenant id is trusted anywhere in `app/api`); 21 services
apply tenant-scoped `get_or_404` reference validation across 135+ call sites.

## Second remediation pass (master hardening prompt)

| # | Gap | Fix / status |
| - | --- | --- |
| 6 | **Rate limiting had no functional proof.** 26 `@limiter.limit` decorators existed and `register_rate_limit()` *is* called (`app/main.py:72`), but nothing proved a route actually returns 429. A decorator is not evidence of enforcement. | New `tests/unit/test_rate_limit_enforcement.py` drives the **real** `POST /api/v1/auth/login` past the 20/minute budget and asserts a real `429` with the `rate_limited` envelope. `IMPLEMENTED AND VERIFIED`. |
| 7 | **Production could run the limiter on `memory://`.** `_validate_redis_url()` returned early when `REDIS_URL` was empty, so a multi-replica deployment gave each process its own counter and the effective limit became N x `RATE_LIMIT_STRICT` - throttling silently diluted rather than absent. | `validate_for_production()` now requires `REDIS_URL`. Dev/test unaffected. |
| 8 | **60-minute access tokens combined with browser-storage tokens** gave a long silent-exfiltration window. | `ACCESS_TOKEN_EXPIRE_MINUTES` 60 -> **15**, with the reasoning documented in `config.py`. Not chosen blindly: refresh-on-401 with request deduplication already exists in `api-client.ts`, and revocation never depended on this value (`tv` is checked every request). |

## Known residual risks (not closed here)

1. **Tokens in `localStorage`.** `frontend/src/lib/session.ts` persists the full
   JWT pair. Compensated by `tv` revocation, family-reuse detection and
   refresh-on-401, but an XSS that reads only the *access* token and uses it
   inside its lifetime triggers no refresh and therefore no detection signal.
   Closing this properly is an architectural decision (HttpOnly-cookie/BFF
   migration, or short-lived in-memory access tokens) that should be taken
   deliberately **before** Phase 6 frontend work, not half-applied mid-task.
2. **Finding B is partially closed.** The three known cross-tenant ID paths are
   fixed and the `get_or_404` pattern is widespread, but no exhaustive
   route-by-route negative-test sweep exists for admin/internal endpoints,
   worker paths and AI tool entry points.
3. **`refresh()` does not re-challenge MFA.** Standard practice, but it means a
   long-lived refresh chain never re-proves the second factor.
4. **`Retry-After` is dropped on the IP-level limiter path.** `headers_enabled=True`
   is set, but the project's own `RateLimitExceeded` handler returns only the
   error envelope. Account lockout *does* send `Retry-After`; the shared limiter
   does not, so clients cannot back off precisely. Pinned by
   `test_limiter_429_omits_retry_after_known_gap`.
5. **AI-layer security is untouched** by this task (prompt injection, excessive
   agency, vector/embedding tenant isolation, tool egress, unbounded
   consumption) — correctly out of scope for an auth gate.
