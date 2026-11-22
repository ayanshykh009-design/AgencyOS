# AgencyOS Phase 6 — Batch 5 Security Review

**Document:** `docs/PHASE6_BATCH5_SECURITY_REVIEW.md`
**Scope:** Batch 5 (`/ai`, `/ai/settings`, `/founder`, `/founder/proposals`, `/founder/intelligence`) under `B5-PLAN-v1.0`
**Baseline HEAD:** `7f53ffaa5456b7ef7d1f58d8a441c086bf05fac0`
**Date:** 2026-11-21

---

## 1. Review outcome

No P0/P1/P2/P3 security defect remains in the Batch 5 scope. Backend permission enforcement is unchanged and remains the source of truth; the new capability surface exposes only six non-secret booleans; tenant isolation is derived server-side; feature flags fail closed; keys remain server-side; rate limiting and the unified error envelope are preserved.

---

## 2. Authorization (RBAC)

### 2.1 Backend is authoritative

Existing dependencies were not weakened. Relevant routes retain:

| Route | Required permission |
|---|---|
| `POST /api/v1/ai/run` | `AI_RUN` |
| `POST /api/v1/ai/dispatch` | `LEAD_WRITE` |
| `GET /api/v1/ai/settings` | any authenticated user (non-secret config read; matches `docs/api/endpoints/ai.md`) |
| `PATCH /api/v1/ai/settings` | `AI_MANAGE` |
| `POST /api/v1/agents/runs/{id}/cancel` | `AGENT_MANAGE` |
| Founder reads | `FOUNDER_READ` |
| Founder chat / conversation delete / proposal decide | `FOUNDER_MANAGE` |
| Intelligence reads | `FOUNDER_READ` |
| Intelligence triage / acknowledge / dismiss | `FOUNDER_MANAGE` |

Frontend permission helpers (`frontend/src/lib/batch5-permissions.ts`) map to the canonical `can()` matrix in `frontend/src/lib/permissions.ts`, which matches `backend/app/core/permissions.py`. They are UX-only; a hidden or disabled control is not treated as an authorization boundary.

### 2.2 Specific gaps closed

- `/ai` now has a page-level `ai_run` gate; a viewer/member without `ai_run` sees a permission panel and no run controls.
- Cancel is restricted to `agent_manage` (owner/admin only), matching the backend cancel route and D-13. No backend permission was broadened.
- `/founder` has a page-level `founder_read` gate; send, delete, and inline approve/deny are restricted to `founder_manage`.
- `/founder/proposals` decisions remain `founder_manage`; `/founder/intelligence` triage remains `founder_manage`.
- `/ai/settings` retains `ai_manage`.

Role-matrix tests cover owner, admin, manager, member, sales_agent and viewer, including an explicit assertion that Cancel is admin/owner only.

---

## 3. Multi-tenant isolation

- `GET /api/v1/ai/capabilities` accepts **no** organization identifier from the client. It derives the org from `current_user.organization_id` and calls `AIService(db).is_ai_enabled(...)` with that server-derived value.
- `frontend/src/services/ai.ts` issues a bare GET to `/ai/capabilities` with no payload and no org field.
- No mutation route gained a client-selectable org parameter. Existing repository/RLS scoping is unchanged.
- `AICapabilitiesRead` contains exactly six boolean fields. No organization ID, user data, model configuration, hostname, or provider identity is returned.

---

## 4. Secrets and capability disclosure

- Provider keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`) remain server-side environment variables. No key value is logged, returned, or referenced in browser code.
- Root `.env.example` additions are empty or safe defaults (`false`, `0`, empty string); no real credentials were added.
- The capability endpoint's API test asserts the exact six-key payload and scans for secret-like field names.
- No `NEXT_PUBLIC_*` secret was introduced; the session store keeps only a short-lived in-memory access token, with the refresh token in an HttpOnly cookie.

---

## 5. Fail-closed behavior

- All AI/Founder/intelligence feature flags default to `False` in `backend/app/core/config.py`; budgets default to `0`.
- `LLMService._enforce_budget` denies when both token and cost budgets are `<= 0`; `ai_budget_configured` reports the exact logical complement (`> 0 OR > 0`).
- `AIService.is_ai_enabled()` now distinguishes a missing `ai` key (no override → enabled, preserving new-org behavior) from malformed non-dict `ai` data (denied), with `kill_switch=True` authoritative. Previously malformed data failed open.
- Every frontend page initializes capability state to `null` and keeps it `null` on fetch failure. Pure helpers return a disable reason for `null`, so no action is enabled while capability state is unverified.
- Disabled-reason precedence is kill switch → budget → feature flag, matching backend evaluation.
- Truthful disabled states are rendered for agent runtime off, founder assistant off, triage off, organization kill switch on, and budget not configured. No page claims availability when the default deployment denies it.
- Neither the triage flag nor the capability endpoint changes read access to intelligence signals: reads remain available while triage is off, matching the backend contract.

---

## 6. Request hardening

- The new endpoint uses `@limiter.limit(settings.RATE_LIMIT_DEFAULT)` and declares `response: Response`, so slowapi's header injection cannot produce the R7 post-handler 500. Tests assert the rate-limit headers.
- The repo-wide rate-limit guard floor was raised from 22 to 23 and the AI-local assertion from 5 to 6, keeping the anti-vacuity guard tight after the new handler.
- Errors continue through the unified envelope in `backend/app/core/errors.py` / `ErrorResponse`; no stack trace or raw provider error is exposed. New API tests assert the structured 401 envelope.
- No new audit event was invented; existing domain tables remain the evidence trail.
- Existing request-ID/security middleware, structured logging, and production config validation are unchanged.

---

## 7. Client-side safety

- All five routes retain their `"use client"` boundaries; hooks precede conditional returns; polling and capability fetches use cancellation guards.
- Founder event handlers use mounted and monotonic request-sequence guards, preventing post-unmount state writes and wrong-thread response rendering. The delete handler refreshes the tenant-scoped list even when the active thread changes mid-request, then only guards the local thread reset.
- The inline decision handler has an in-flight guard and disables both Approve and Deny while a decision is pending, preventing duplicate submissions.
- No fake success state, fake API, or hidden route was introduced. All service wrappers call real backend endpoints.

---

## 8. Residual risks and out-of-scope observations

- **PASS** — the first `next build` advisory nudge was investigated; no applicable GHSA affects installed `next@16.4.6`. No Next.js upgrade was justified, while integrated dependency-security remediation patched Vitest/`@vitest/mocker` to 4.1.12 and added the Vite 8.2.4 override.
- Browser-level interactivity/hydration was NOT VERIFIED in the Batch 5 baseline (SSR tests covered initial static markup only); integrated synthetic browser QA later exercised the canonical routes with fresh accounts and real clicks. Real-stack browser proof remains NOT VERIFIED.
- Live DB/Redis validation was NOT VERIFIED in the Batch 5 baseline. Integrated qualification proved disposable PG16 connectivity and disposable Redis behavior, but full migration-backed DB/RLS runtime proof remains BLOCKED BY ENVIRONMENT.
- Pre-existing, not introduced or changed by Batch 5: founder status-filter query-parameter mismatch (`founder.ts` sends `status`, backend declares `proposal_status`), nested interactive delete control in the conversation list, `Makefile` gate drift, and `COMMUNICATION_LAYER_ENABLED` with no runtime consumer. These require separate authorization and are excluded from this batch's verdict.

---

## 9. Conclusion

Batch 5 does not weaken any authentication, authorization, tenant-isolation, secret-handling, rate-limiting, or error-handling control. The changes strictly reduce previously over-permissive client behavior and replace implied availability with backend-authoritative truth. No in-scope security defect remains.
