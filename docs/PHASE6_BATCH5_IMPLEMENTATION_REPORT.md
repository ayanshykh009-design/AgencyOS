# AgencyOS Phase 6 — Batch 5 (AI + Founder) Implementation Report

**Document:** `docs/PHASE6_BATCH5_IMPLEMENTATION_REPORT.md`
**Execution contract:** `docs/PHASE6_BATCH5_IMPLEMENTATION_PLAN.md`, `B5-PLAN-v1.0` (FROZEN)
**Branch:** `feat/phase6-commercial-v1`
**Baseline HEAD:** `7f53ffaa5456b7ef7d1f58d8a441c086bf05fac0` (local and upstream)
**Date:** 2026-11-21

---

## 1. Executive summary

Batch 5 delivered the five canonical routes (`/ai`, `/ai/settings`, `/founder`, `/founder/proposals`, `/founder/intelligence`) as corrections to an existing real-backend implementation. No route was rebuilt, no architecture was replaced, no migration was added, and no dependency was introduced.

The implementation adds a backend-authoritative, non-secret capability surface so the UI can render truthful disabled states, closes client- and server-side authorization gaps, hardens a kill-switch fail-closed path, and adds page/service/contract tests plus documentation drift corrections.

All executable gates available locally pass. Audit rounds and their outcomes are recorded in §6, including the R7 process finding that was corrected by re-auditing with a frozen tree. Limitations (live DB/Redis, browser hydration, Next.js advisory) are recorded in §6 and in the final acceptance report; nothing is claimed as verified unless it was actually executed.

---

## 2. Plan quality gate

| Run | Result | Detail |
|---|---|---|
| First | **FAIL (16/17)** | §F.4 conflated a missing `settings.ai` key with malformed non-dict `settings.ai`; would have disabled AI for every new org. |
| Final | **PASS (17/17)** | Branches split (missing → enabled, malformed → denied), `canView` defined, unified error envelope named, concrete service-test list added. |

Plan frozen as `B5-PLAN-v1.0` only after the final 17/17 PASS.

---

## 3. Files changed

### 3.1 Backend and shared docs

| File | Change |
|---|---|
| `backend/app/schemas/ai.py` | Added `AICapabilitiesRead` (exactly six booleans; no secrets). |
| `backend/app/api/v1/endpoints/ai.py` | Added authenticated, rate-limited `GET /api/v1/ai/capabilities` with `response: Response` and org derived from `CurrentUser`. |
| `backend/app/services/ai_service.py` | `is_ai_enabled()` now treats a missing `ai` key as enabled and malformed non-dict `ai` as denied; kill switch remains authoritative. |
| `backend/tests/unit/test_ai_service.py` | Added three regression cases (missing key / malformed value / `kill_switch=True`). |
| `backend/tests/api/test_ai_capabilities_api.py` *(new)* | 401 envelope, exact six-boolean payload, org derivation, no secret-like fields, rate-limit headers, all-false fail-closed case. |
| `backend/tests/unit/test_rate_limited_handler_contract.py` | Raised AI inventory assertion 5→6 and repo-wide floor 22→23 after the new rate-limited handler. |
| `docs/api/endpoints/ai.md` | Documented capability endpoint (fields, sources, statuses, auth table); added `kill_switch` to the settings contract. |
| `docs/database.md` | Added M8/M9 tables 47–50 and the `intelligence_signals` mirror limitation; corrected row 48 to `sender_type user`/`assistant` with tenant-scoped RLS reads/writes. |
| `backend/app/core/config.py` | Comment-only correction: budget `0` = not configured, fails closed; never "unlimited". |
| `.env.example` | Added safe, non-secret AI budget and M6/M8/M9 flag defaults plus empty `GEMINI_API_KEY=`. |
| `database/schema/14_founder.sql` | Column mirror `metadata_` → `metadata` (mirrors migration `0030` and the ORM). |

### 3.2 Frontend

| File | Change |
|---|---|
| `frontend/src/types/index.ts` | Added `AICapabilities`; added `kill_switch` to `OrganizationAISettings`. |
| `frontend/src/services/ai.ts` | Added `getAICapabilities()` → `GET /ai/capabilities`. |
| `frontend/src/lib/ai-capabilities.ts` *(new)* | Pure fail-closed reason helpers with kill-switch → budget → flag precedence. |
| `frontend/src/lib/batch5-permissions.ts` *(new)* | Pure permission helpers over the existing `can()` matrix. |
| `frontend/src/app/(dashboard)/ai/page.tsx` | `ai_run` page gate; run/cancel/dispatch gating; truthful disabled reasons; polling preserved. |
| `frontend/src/app/(dashboard)/ai/settings/page.tsx` | Kept `ai_manage`; added read-only capability notices. |
| `frontend/src/app/(dashboard)/founder/page.tsx` | `founder_read` page gate; `founder_manage` mutations; capability-gated send/decide; in-flight and request-race guards. |
| `frontend/src/app/(dashboard)/founder/proposals/page.tsx` | `founder_read` gate; `founder_manage` + kill-switch decision gating; removed dead `refresh()`. |
| `frontend/src/app/(dashboard)/founder/intelligence/page.tsx` | `founder_read` gate; triage control truthfully disabled when flag off. |
| `frontend/src/services/__tests__/ai.test.ts` | Added capability, `getAgentRun`, `cancelAgentRun` tests; settings payload includes `kill_switch`. |
| `frontend/src/services/__tests__/founder.test.ts` | Added conversation fetch/delete tests. |
| `frontend/src/lib/ai-capabilities.test.ts` *(new)* | Reason precedence, null fail-closed, all-allowed cases. |
| `frontend/src/lib/batch5-permissions.test.ts` *(new)* | Full role matrix; Cancel restricted to admin/owner. |
| `frontend/src/app/(dashboard)/ai/batch5-ssr.test.tsx` *(new)* | Static-markup permission and disabled-state cases. |
| `frontend/src/app/(dashboard)/founder/batch5-ssr.test.tsx` *(new)* | Static-markup permission, disabled-state, and decision-busy cases. |

---

## 4. Defects fixed

### 4.1 Planned defects (frozen plan §E)

| ID | Severity | Fix |
|---|---|---|
| B5-F-01 | P1 | Cancel now gated by `agent_manage`. |
| B5-F-02 | P1 | `/ai` page-level `ai_run` gate; no controls for unauthorized viewers. |
| B5-F-03 | P1 | Founder read/mutation gates; inline approve/deny restricted to `founder_manage`. |
| B5-F-04 | P1 | Truthful disabled states driven by backend capability flags/kill switch/budget. |
| B5-B-01 | P1 | Added non-secret `GET /api/v1/ai/capabilities`. |
| B5-B-02 | P1 | Malformed per-org `settings.ai` now fails closed; missing key still defaults to enabled. |
| B5-T-01 | P2 | Frontend service/page tests and backend capability tests added. |
| B5-D-01 | P2 | Capability API documented. |
| B5-D-02 | P3 | Schema mirror column corrected. |
| B5-D-03 | P3 | M8/M9 tables documented with mirror limitation. |
| B5-D-04 | P3 | Budget comment corrected to fail-closed semantics. |
| B5-D-05 | P3 | Root env template aligned with backend flags/budgets. |

### 4.2 Defects found by the autonomous audit loop

| Round | Severity | Defect | Fix |
|---|---|---|---|
| R1 | P3 | `docs/database.md` row 48 mislabeled `founder_messages` as "append-only" | Reworded to tenant-scoped reads/writes via RLS. |
| R1 | P3 | Repo-wide rate-limit guard floor left at 22 after the 6th AI handler | Raised to 23; comment updated. |
| R2 | P3 | Row 48 listed `sender_type` as `founder`/`assistant`/`system` | Corrected to the real enum values `user`/`assistant`. |
| R3 | P3 | Dead `refresh()` in founder proposals page | Removed. |
| R3 | P3 | Founder event handlers wrote state after awaits without mount/request guards | Added `mountedRef` and `conversationSeqRef` guards. |
| R3 | P3 | `onDecide` had no in-flight guard | Added `decidingId` guard and `busy` prop disabling both buttons. |
| R4 | P2 | Stale-closure race: switching threads mid-send/delete could write the wrong thread | Captured `seq` at handler start and guarded post-await writes. |
| R4 | P3 | New `busy` prop had no regression test | Added SSR case asserting both buttons disabled. |
| R5 | P3 | `onDelete` seq guard skipped the sidebar refresh after a successful delete | Refresh first while mounted, then guard only the active-thread reset. |
| R8 | P3 | Security review misstated the AI settings gate as `GET/PUT` with `AI_MANAGE`; source is `GET` (any authenticated) and `PATCH` (`AI_MANAGE`) | Split the row in `docs/PHASE6_BATCH5_SECURITY_REVIEW.md` into the accurate `GET`/`PATCH` rows, matching `docs/api/endpoints/ai.md` and the frontend `PATCH` call. |
| R9 | P3 | Acceptance report stated stale audit totals (seven rounds / nine defects) that contradicted the §4.2 and §6 logs after R8 | Replaced the fixed counts with a reference to the authoritative §4.2/§6 logs so the claim cannot go stale again. |
| R10 | P3 | §4.2 closing line claimed the R9 fix had been "re-verified with gates and subsequent audit rounds" before R10/R11 returned | Replaced with a factual pointer to the round-by-round verdicts in §6 and gate results in §5. |

The table records every in-scope defect found and the fix applied at the time. Round-by-round verdicts are in §6; executable gate results are in §5.

---

## 5. Gate results

### 5.1 Backend (from `D:\AgencyOS\backend`, `.venv\Scripts\python.exe`)

| Gate | Result |
|---|---|
| `pytest tests/unit tests/api -p no:warnings` | **PASS — 1693 passed** (Batch 5 freeze baseline, 58.39s) |
| `pytest -p no:warnings` (full suite) | **PASS — 1942 passed, 101 skipped, 0 failed** (integrated final rerun, 109.13s; Batch 5 freeze baseline was 1871 passed, 101 skipped) |
| `ruff check app tests` | **PASS — All checks passed** |
| `mypy app` | **PASS — no issues in 355 source files** |
| `pytest tests/unit/test_rate_limited_handler_contract.py` | **PASS — 8 passed** |
| `scripts/ci/contract_diff.py` | Executed; 177 backend routes, 108 frontend calls; pre-existing caller drift warnings; `/api/v1/ai/capabilities` correctly has a frontend caller |
| `scripts/ci/docs_api_consistency.py` | Executed; 159/177 routes documented; 18 pre-existing gaps; new endpoint documented |

### 5.2 Frontend (from `D:\AgencyOS\frontend`)

| Gate | Result |
|---|---|
| `npm run typecheck` | **PASS** |
| `npm test` | **PASS — 51 files, 360 tests in the final integrated rerun** (Batch 5 baseline: 46 files, 332 tests) |
| `npm run lint` | **PASS — 0 errors, 1 pre-existing warning** (`postcss.config.mjs`) |
| `npm run build` | **PASS** — compiled, TypeScript clean, 38 static pages generated |
| `npm run format:check` | 18 pre-existing drift files in the integrated tree; none are Batch 5/6 files |

### 5.3 Next.js advisory

The first Batch 5 `next build` run stopped with a `SecurityFatalError` advisory nudge; retrying the identical command completed successfully with a warning. Integrated investigation found no applicable GHSA for installed `next@16.4.6`, so no Next.js upgrade was made. Dependency-security remediation patched Vitest/`@vitest/mocker` to 4.1.12 and added the Vite 8.2.4 override.

---

## 6. Audit loop

| Round | Backend stream | Frontend stream | Action |
|---|---|---|---|
| R1 | NOT CLEAN — 2 P3 | CLEAN | Fixed both P3 defects |
| R2 | NOT CLEAN — 1 P3 | CLEAN | Fixed row-48 enum mislabel |
| R3 | CLEAN | NOT CLEAN — 3 P3 | Fixed dead code, race guards, in-flight guard |
| R4 | CLEAN | NOT CLEAN — 1 P2 + 1 P3 | Fixed stale-closure race and added busy test |
| R5 | CLEAN | NOT CLEAN — 1 P3 | Fixed `onDelete` refresh ordering |
| R6 | **CLEAN** | **CLEAN** | First consecutive clean round |
| R7 | **NOT CLEAN (process)** | CLEAN | R7 backend correctly identified that final report files were created during the audit and that R7 had been pre-declared clean in this report before its verdict existed. No code defect was found; the process defect is recorded here and corrected by re-running audits with a fully frozen tree. |

The R6 round was the first consecutive clean round. Because the tree changed while R7 was in progress (final reports being written), R7 does not count toward the two-consecutive-clean requirement. The termination condition is satisfied only by the post-report audit rounds recorded below.

### Post-report audit rounds

All four mandatory documents are now final and these rounds ran with a frozen tree (no file writes or gate executions during any audit).

| Round | Backend stream | Frontend stream | Action |
|---|---|---|---|
| R8 | NOT CLEAN — 1 P3 | NOT CLEAN — same 1 P3 | Both streams independently found the security-review settings-gate drift; fixed by splitting the row into accurate `GET` (any authenticated) and `PATCH` (`AI_MANAGE`) entries. No code defect. |
| R9 | CLEAN | NOT CLEAN — 1 P3 | Backend clean. Frontend found stale audit totals in the acceptance report; fixed by referencing the authoritative §4.2/§6 logs instead of fixed counts. |
| R10 | NOT CLEAN — 1 P3 | CLEAN | Frontend clean. Backend found that the §4.2 closing line claimed the R9 fix had been re-verified before R10/R11 returned; replaced with a purely factual pointer to §5 and §6. |
| R11 | **CLEAN** | **CLEAN** | First consecutive clean round on the frozen tree; zero unresolved in-scope P0/P1/P2/P3 defects in either stream. |
| R12 | **CLEAN** | **CLEAN** | Second consecutive clean round on the unchanged frozen tree; zero unresolved in-scope P0/P1/P2/P3 defects in either stream. |

**Termination condition met:** R11 and R12 are two consecutive audit rounds in which both the backend/contract/tests stream and the frontend/UI/security stream reported zero unresolved in-scope P0/P1/P2/P3 defects. The edit that records these two verdicts is documentation-only; it changes no application code, contract, test, or audited surface. R11 and R12 ran on a tree that was frozen before either began.

---

## 7. Limitations and not-verified items

- Live PostgreSQL/Redis/container validation: **NOT VERIFIED in the Batch 5 baseline** — `psql`, `docker`, `redis-cli` were not available in PATH. Integrated qualification later used disposable PG16/Redis for scoped checks; full migration-backed DB/RLS proof remains `BLOCKED BY ENVIRONMENT`.
- Browser hydration, click-handler interactivity and visual QA: **NOT VERIFIED in the Batch 5 baseline** — SSR tests cover static markup only by design (plan §G.7); integrated synthetic browser QA later exercised the canonical routes with real clicks.
- Live paid AI calls: intentionally **not executed**; all AI tests are mocked/deterministic.
- `gh` CLI unavailable; baseline CI was verified through the GitHub REST API.
- Global `python` lacks `pyotp`; all backend gates were run with `backend/.venv`.
- Pre-existing, out-of-scope observations recorded but not changed: founder status-filter query-param mismatch (`founder.ts` `status` vs backend `proposal_status`), nested interactive delete control, `Makefile` gate drift, `COMMUNICATION_LAYER_ENABLED` with no consumer, and missing canonical route 36 / legacy redirects.

---

## 8. Preservation statement

No `git add`, commit, push, force-push, merge, checkout of `main`, deploy, PR change, Batch 6/7 work, reset, clean, stash or discard was performed. The staging area is empty. All pre-existing user-owned artifacts remain untouched, including the protected `database/migrations/0016_search_trigram_indexes.sql`, which was never opened, read, inspected, diffed, hashed, staged, modified, renamed or deleted.
