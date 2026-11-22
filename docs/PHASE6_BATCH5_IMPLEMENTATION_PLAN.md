# AgencyOS Phase 6 — Batch 5 (AI + Founder) Implementation Plan

**Document:** `docs/PHASE6_BATCH5_IMPLEMENTATION_PLAN.md`  
**Plan version:** `B5-PLAN-v1.0`  
**Mode:** PLAN → EXECUTE (same authorized run); no commit, push, merge, deploy, PR change, or `main` change  
**Branch:** `feat/phase6-commercial-v1`  
**Baseline HEAD:** `7f53ffaa5456b7ef7d1f58d8a441c086bf05fac0` (local and upstream)  
**Baseline CI:** GitHub Actions run `#74`, SHA `7f53ffaa5456b7ef7d1f58d8a441c086bf05fac0`, `conclusion: success`, 5/5 jobs success (verified via GitHub REST API; `gh` CLI unavailable)  
**Date:** 2026-11-21  
**Status:** DRAFT — pending independent 17-check plan quality gate; execution is not authorized until the gate result is appended in §L.

---

## A. Executive summary

Batch 5 is exactly the five canonical routes in the commercial V1 inventory:

1. `/ai`
2. `/ai/settings`
3. `/founder`
4. `/founder/proposals`
5. `/founder/intelligence`

All five pages and their typed service wrappers already exist and call real backend endpoints. This is **not** a build-from-scratch batch. The verified defects are authorization/UX mismatches, absence of a backend-authoritative capability surface for feature-flagged states, missing Batch 5 page/hook tests, and small schema/documentation drift.

The implementation will:

- add a small, authenticated, read-only backend capability endpoint (`GET /api/v1/ai/capabilities`) that exposes **non-secret deployment and organization capability booleans** so the UI can render truthful disabled states instead of implying availability;
- gate `/ai` on `ai_run` and Cancel on `agent_manage` (D-13/G-09; canonical plan line 89);
- gate founder chat writes and inline proposal decisions on `founder_manage`, and add page-level `founder_read` gating;
- disable/run-block AI, founder chat, and manual triage controls when the corresponding backend flags, organization kill switch, or budget preconditions fail closed;
- add page-level SSR/markup tests and service tests; add backend API/unit coverage for the capability contract;
- correct Batch 5-adjacent schema mirror, config comment, environment template, and database documentation drift.

No schema migration is added. No LLM provider, agent runtime, approval state machine, RLS policy, or authentication model is replaced. No live paid AI call is made. No globally enabled AI flag is introduced.

---

## B. Verified baseline and preservation constraints

### B.1 Git and CI evidence

| Item | Verified value |
|---|---|
| Branch | `feat/phase6-commercial-v1` |
| Local HEAD | `7f53ffaa5456b7ef7d1f58d8a441c086bf05fac0` |
| Upstream HEAD | `7f53ffaa5456b7ef7d1f58d8a441c086bf05fac0` |
| `main` | `e020aae3996b52cf4e265ea1315e80afc34e24ad`; never checked out or changed |
| PR #2 | Head matches baseline SHA; must remain unchanged |
| CI | Run #74, 5/5 success on baseline SHA |
| `gh` | Unavailable (`'gh' is not recognized…`); REST API used instead |

### B.2 Working-tree preservation

The baseline working tree is dirty. All pre-existing modified and untracked files are **user-owned artifacts** and must be preserved byte-for-byte except where this plan explicitly lists a Batch 5 file for edit.

Protected file:

- `database/migrations/0016_search_trigram_indexes.sql` — never read, opened, inspected, diffed, hashed, staged, modified, renamed, or deleted.

Explicit prohibitions for this run:

- no `git add .`, `git add -A`, staging of unknown files, commit, push, force-push, merge, checkout of `main`, deploy, PR #2 change, Batch 6, or Batch 7;
- no reset/clean/stash/discard of any kind;
- no unapproved dependency;
- no weakening of middleware, rate limiting, RBAC, tenant scoping, structured logging, or production config validation;
- no fake success state or fake API.

### B.3 Tool availability limitations

- `psql`, `docker`, and `redis-cli` are not in PATH. Live PostgreSQL/Redis/container validation is NOT VERIFIED locally; CI evidence and DB-free tests are used, and this limitation is reported honestly.
- Browser-based visual QA may be unavailable; if it cannot be executed it is reported as NOT VERIFIED, never as PASS.
- `gh` is unavailable; GitHub REST API was used for CI verification.

---

## C. Canonical sources inspected

| Source | Authority used |
|---|---|
| `docs/PHASE6_COMMERCIAL_V1_IMPLEMENTATION_PLAN.md` | Batch 5 definition; real-backend-only; truthful unavailable states; no fake success |
| `AGENCYOS_PHASE6_MASTER_IMPLEMENTATION_BLUEPRINT.md` §4/#25–29, §4.2, §7, §9 | Batch E route inventory; one central internal Agent; no separate user-facing agents; respect runtime/triage flags; verify cancellation and approval permissions |
| `docs/phase6/PHASE6_IMPLEMENTATION_STRUCTURE_AND_PLAN.md` lines 89–93 | Route 25 cancellation = backend-enforced `AGENT_MANAGE`; route 26 `AI_MANAGE`; route 27 founder flag; route 29 triage gated |
| `docs/AGENCYOS_PHASE6_DECISION_REGISTER.md` D-02, D-13, D-18 | Evidence and recommendations only; no new product decision made on owner's behalf |
| `docs/api/endpoints/ai.md`, `docs/api/endpoints/founder.md` | Existing API contract documentation |
| `AGENCYOS_ALL_IN_ONE.pdf` (extracted text in temp) | Batch 5 screen evidence for screens 21–23; visual fidelity limitation acknowledged |
| `backend/app/api/v1/api.py` | Router mount evidence |
| `backend/app/api/v1/endpoints/{ai,agents,founder_chat,intelligence}.py` | Authoritative routes, permissions, flags, error codes |
| `backend/app/core/permissions.py`, `backend/app/core/config.py` | Permission enum and flag defaults |
| `backend/app/services/{ai_service,founder_chat_service,founder_action_service}.py` | Business logic and kill-switch behavior |
| `backend/app/llm/service.py`, `backend/app/llm/providers/__init__.py` | Existing provider abstraction, retries, fail-closed budgets |
| `backend/app/agents/*`, `backend/app/ai/*`, `backend/app/tools/registry.py` | Single-agent runtime, state machine, tool authorization |
| `frontend/src/app/(dashboard)/ai/page.tsx` | `/ai` run/poll/cancel/dispatch UI and known gaps |
| `frontend/src/app/(dashboard)/ai/settings/page.tsx` | `/ai/settings` provider/model form; `ai_manage` gate |
| `frontend/src/app/(dashboard)/founder/page.tsx` | Founder chat, conversation delete, inline proposal decisions |
| `frontend/src/app/(dashboard)/founder/proposals/page.tsx` | Approval queue; `founder_manage` decision gate |
| `frontend/src/app/(dashboard)/founder/intelligence/page.tsx` | Signal feed; ack/dismiss and triage controls |
| `frontend/src/services/{ai,founder,intelligence}.ts` | Real API wrappers and React Query hooks |
| `frontend/src/lib/permissions.ts`, `frontend/src/proxy.ts` | Client RBAC mirror and protected route families |
| Backend/frontend test suites and CI scripts | Existing coverage and gate inventory |

---

## D. Exact scope

### D.1 In scope

- The five canonical Batch 5 routes only.
- Backend capability endpoint and schema for non-secret flags.
- Frontend permission and disabled-state corrections on those five pages.
- Frontend services/types/tests for the capability contract and page states.
- Backend API/unit tests for the capability endpoint.
- Batch 5 API documentation.
- Explicit Batch 5-adjacent drift corrections listed in §E.4.
- Autonomous bug discovery/fix/re-audit loop until two consecutive clean audits with zero unresolved in-scope P0/P1/P2/P3 defects.

### D.2 Out of scope

- Batch 6 automation routes, Batch 7 brand routes, canonical route 36 `/settings/account`, and three legacy redirects (missing in code but outside Batch 5).
- Public chatbot, generic `/approvals`, `/memory`, `/ai/runs`, multi-agent hub, new AI personas, or invented AI claims.
- New LLM provider, provider failover, MCP server, architecture replacement, prompt rewrite, agent-runtime rewrite, or approval flow rewrite.
- New migration, RLS change, index change, or secret in code/browser.
- Live paid AI calls; all AI tests remain deterministic/mocked.
- Globally enabling any feature flag.
- Dependency additions.
- Commit/push/merge/deploy/PR/main changes.

### D.3 Blueprints and exclusions preserved

One central internal Agent only. `/founder/proposals` remains the sole V1 Assistant Actions approval surface. No public chatbot or generic AI/approval/memory routes.

### D.4 Owner decision register handling

| ID | Status in this run | Handling |
|---|---|---|
| D-02 `/ai` composition | **REQUIRES FOUNDER DECISION** (visual composition) | No redesign; preserve current single-central-Agent layout. No multi-agent UI added. |
| D-13 Cancel permission | Implemented per canonical source: UI gate with `agent_manage`; backend unchanged. | No backend permission broadening. |
| D-18 flagged routes | **REQUIRES FOUNDER DECISION** (ship disabled vs hidden) | Canonical plan requires truthful unavailable states; implementation uses backend-authoritative disabled states and does not hide core routes. This is an implementation of an existing canonical requirement, not a new product choice. |
| D-01/D-03–D-12/D-14–D-17 | Not Batch 5 decisions; unchanged | No decision made. |

---

## E. Defect inventory and remediation contract

Severity scale: P0 = production/data/security break; P1 = wrong authorization or false availability; P2 = missing test/documentation contract; P3 = drift/cosmetic that can mislead operators.

| ID | Severity | Evidence | Fix |
|---|---|---|---|
| B5-F-01 | P1 | `ai/page.tsx:155–167,260–264` shows Cancel without `agent_manage`; backend cancel requires `AGENT_MANAGE` | Gate Cancel with `can(role,"agent_manage")`; test viewer/member/admin rendering |
| B5-F-02 | P1 | `/ai` has no page-level `ai_run` gate; backend `/ai/run` requires `AI_RUN` | Add permission panel for users without `ai_run`; avoid loading/action controls for them |
| B5-F-03 | P1 | `founder/page.tsx` send/delete/inline approve-deny available to non-managers; backend chat/decide/delete require `FOUNDER_MANAGE` | Add `founder_read` page gate; `founder_manage` gate for send, delete, and inline decisions |
| B5-F-04 | P1 | All flagged capabilities default off in `config.py`; UI appears enabled; agent runtime off queues runs that never execute, founder executor returns disabled text, triage returns 503 only after click | Add backend capability endpoint; pages fail closed and render truthful disabled notices |
| B5-B-01 | P1 | No safe backend surface tells the browser whether runtime/founder/triage/kill switch/budget are available | Add `GET /api/v1/ai/capabilities` returning non-secret booleans only |
| B5-B-02 | P1 | `AIService.is_ai_enabled()` docstring says malformed `settings.ai` fails closed, but `ai_service.py:150–153` returns `True` when `ai` is not a dict | Return `False` for malformed `settings.ai`; add unit regression test; no behavior change for valid settings |
| B5-T-01 | P2 | No Batch 5 page/hook tests; `test_ai_api.py` has only unauthenticated 401 checks; service tests miss capability, `getAgentRun`, cancel, conversation fetch/delete | Add `getAICapabilities`, `getAgentRun`, `cancelAgentRun`, `getFounderConversation`, `deleteFounderConversation` service tests; add SSR/markup page tests; add backend capability API test |
| B5-D-01 | P2 | `docs/api/endpoints/ai.md` does not document capability surface | Add endpoint documentation in same change |
| B5-D-02 | P3 | `database/schema/14_founder.sql:23` uses `metadata_`; migration `0030` renamed to `metadata`; ORM maps to `metadata` | Correct schema mirror line only; no migration |
| B5-D-03 | P3 | `docs/database.md` stops at table 46 and omits M8/M9 tables | Add M8/M9 table rows and note intelligence signal schema mirror limitation |
| B5-D-04 | P3 | `config.py:263–266` comment says budget `0` means unlimited, but `llm/service.py:237–246` fails closed | Correct comment to match enforced behavior |
| B5-D-05 | P3 | Root `.env.example` omits AI budgets and M6/M8/M9 flags present in `backend/.env.example` | Add safe, empty/default template entries only |

### E.1 Explicitly out-of-scope observations (tracked, not Batch 5 defects)

- Budget-zero semantic conflict behavior itself: code and tests agree on fail-closed; only the stale comment is corrected.
- `default_client()` base-url fallback, dead config knobs, MCP server absence, provider failover absence, unified activity events absence, founder chat trace correlation, and founder chat bypass of `AgentRuntime`: pre-existing cross-cutting behavior requiring separate owner-scoped work; no change in Batch 5.
- Makefile gate drift (`verify-contract` path, `lint` omits `mypy`, `ci` omits `npm run build`): reported as gate limitation; direct commands are executed. Changing global CI is not a Batch 5 product fix.
- `COMMUNICATION_LAYER_ENABLED` has no runtime consumer: outside Batch 5.

---

## F. Backend implementation plan

### F.1 New capability contract

Add to `backend/app/schemas/ai.py`:

```python
class AICapabilitiesRead(BaseModel):
    agent_runtime_enabled: bool
    founder_assistant_enabled: bool
    intelligence_triage_enabled: bool
    intelligence_narrative_enabled: bool
    ai_execution_enabled: bool
    ai_budget_configured: bool
```

Field semantics:

| Field | Source | Meaning |
|---|---|---|
| `agent_runtime_enabled` | `settings.AGENT_RUNTIME_ENABLED` | Worker drains queued runs |
| `founder_assistant_enabled` | `settings.FOUNDER_ASSISTANT_ENABLED` | Founder executor may answer |
| `intelligence_triage_enabled` | `settings.INTELLIGENCE_TRIAGE_ENABLED` | Manual sweep permitted |
| `intelligence_narrative_enabled` | `settings.INTELLIGENCE_NARRATIVE_ENABLED` | Narrative generation enabled |
| `ai_execution_enabled` | `await AIService(db).is_ai_enabled(org_id)` | Per-org kill switch inverse; fail closed |
| `ai_budget_configured` | token budget > 0 or cost budget > 0 | Matches `LLMService._enforce_budget` fail-closed preconditions |

No API keys, model names, hostnames, organization IDs, or user data are returned.

### F.2 Endpoint

Add to `backend/app/api/v1/endpoints/ai.py`:

- `GET /api/v1/ai/capabilities`
- authenticated (existing `CurrentUser` dependency); no broader permission required because the payload is non-secret capability state needed by all five pages;
- `@limiter.limit(settings.RATE_LIMIT_DEFAULT)`;
- explicit `response: Response` parameter (slowapi header injection regression R7);
- calls `AIService.is_ai_enabled(current_user.organization_id)` so tenant scoping remains backend-derived;
- returns `AICapabilitiesRead`.

Mount is automatic under the existing `/ai` router; no `api.py` change needed.

### F.3 Tests

- Extend `backend/tests/api/test_rate_limited_success_paths.py` or add a focused API test that:
  - asserts unauthenticated `401` with structured envelope;
  - drives authenticated success with `AIService.is_ai_enabled` patched;
  - asserts rate-limit headers are present;
  - asserts all six booleans are returned and no key material is present.
- Keep all existing AI/founder/runtime/LLM tests intact; no live LLM calls.

### F.4 Kill-switch fail-closed correction

- In `AIService.is_ai_enabled()`, distinguish a **missing** `ai` key from **malformed** `ai` data:
  - `if "ai" not in org.settings: return True` (no override = enabled, preserving new-org behavior);
  - then `ai = org.settings["ai"]`;
  - `if not isinstance(ai, dict): return False` (malformed data fails closed);
  - `return not bool(ai.get("kill_switch", False))`.
- Add unit cases in `backend/tests/unit/test_ai_service.py` proving all three outcomes: missing key → enabled, malformed non-dict → denied, `kill_switch=True` → denied.
- Do not change any other branch of `is_ai_enabled()`.

---

## G. Frontend implementation plan

### G.1 Types and service

- Add `AICapabilities` to `frontend/src/types/index.ts` next to `OrganizationAISettings`.
- Add `getAICapabilities(): Promise<AICapabilities>` to `frontend/src/services/ai.ts`, GET `/ai/capabilities`.
- Extend `frontend/src/services/__tests__/ai.test.ts` to assert URL, method, auth header behavior where applicable, and exact boolean payload parsing.

### G.2 `/ai`

- Add page-level `ai_run` permission panel.
- Load `getAICapabilities()` with existing workspace data.
- Compute:
  - `canRun = can(role,"ai_run") && capabilities.agent_runtime_enabled && capabilities.ai_execution_enabled && capabilities.ai_budget_configured`;
  - `canCancel = can(role,"agent_manage")`;
  - `canDispatch = can(role,"lead_write")`.
- Disable Run AI when `!canRun`; show specific truthful reason(s): organization AI disabled, runtime off, budget not configured, or permission denied.
- Render Cancel only when `canCancel && canView && run is non-terminal`, where `canView = can(role,"ai_run")`; non-viewers see the permission panel and no run controls.
- Preserve run polling, trace display, tool audit, and dispatch behavior; no fake progress or success.

### G.3 `/ai/settings`

- Preserve `ai_manage` gate.
- Add read-only capability notices for runtime off, organization kill switch on, and budget not configured, using the same capability endpoint.
- Keep provider/model save and clear-override behavior unchanged; no secret input is introduced.

### G.4 `/founder`

- Add page-level `founder_read` gate.
- Fetch conversations only for readers.
- Compute `canChat = canManage && capabilities.founder_assistant_enabled && capabilities.ai_execution_enabled && capabilities.ai_budget_configured`.
- Disable Send and show reason when `!canChat`.
- Gate conversation delete and inline Approve/Deny with `founder_manage`; non-managers see proposal cards read-only.
- Preserve approval-gated semantics: the assistant never mutates org data directly.

### G.5 `/founder/proposals`

- Add page-level `founder_read` gate.
- Preserve `founder_manage` decision gate.
- Disable decisions when `capabilities.ai_execution_enabled === false` (backend `decide_proposal` checks org kill switch); show truthful notice.
- Read list/filter remains available.

### G.6 `/founder/intelligence`

- Add page-level `founder_read` gate.
- Keep read endpoints available while triage is off (documented intended behavior).
- Disable “Run triage now” when `!capabilities.intelligence_triage_enabled`; show truthful notice.
- Keep acknowledge/dismiss gated by `founder_manage` and available independently of manual triage, matching backend contract.

### G.7 Tests

- New SSR/markup tests under `frontend/src/app/(dashboard)/ai/` and `frontend/src/app/(dashboard)/founder/` using `renderToStaticMarkup`, mocked `useAuth`, mocked services/hooks, and no new dependency.
- Cases:
  - viewer/member cannot see AI run/cancel controls;
  - admin with runtime off sees disabled AI run and truthful notice;
  - non-manager founder user sees no Send/Delete/Approve/Deny;
  - founder manager with assistant flag off sees disabled Send;
  - intelligence manager with triage off sees disabled Run triage;
  - proposals with org kill switch on sees disabled decisions.
- Reuse existing `vitest` node environment; hydration/browser interactivity remains NOT VERIFIED unless a browser tool is available.

---

## H. Database and schema-mirror plan

- No migration, RLS policy, index, or live database change.
- Correct `database/schema/14_founder.sql` column `metadata_` → `metadata` to mirror migration `0030` and the ORM mapping.
- Update `docs/database.md` with M8/M9 tables:
  - `founder_conversations`
  - `founder_messages`
  - `founder_action_proposals`
  - `intelligence_signals`
- Note that `intelligence_signals` has no `database/schema/` mirror file in this checkout; this is documentation of an existing limitation, not a new schema change.
- Protected `0016` remains untouched.

---

## I. Security and multi-tenant isolation

- Backend derives organization from `CurrentUser`; capability endpoint accepts no org ID from the client.
- Capability payload contains no secrets, keys, hostnames, user lists, or model configuration.
- Existing `require_permission` enforcement on all mutation routes remains unchanged.
- Frontend gates are UX only; backend remains source of truth.
- Fail closed: missing/failed capability fetch disables capability-dependent actions.
- All errors continue through the unified envelope in `backend/app/core/errors.py` / `ErrorResponse`; no error stack traces, no raw provider errors, no token in browser storage.
- Provider keys remain server-side env vars only.
- No new audit events are invented; existing domain tables remain the audit evidence.
- Rate limiting on the new endpoint uses existing default limiter and the `response: Response` pattern.
- All fixed routes already appear in `frontend/src/proxy.ts`; no matcher change is required.

---

## J. Test and gate strategy

### J.1 Commands to execute

Backend (DB-free where possible):

- `python -m pytest tests/unit tests/api -q` from `backend/`
- targeted `ruff check app tests` and `mypy app` if available
- `python -m pytest` full suite attempt; report DB/Redis-dependent skips/failures honestly

Frontend:

- `npm run typecheck`
- `npm run lint`
- `npm test`
- `npm run build`
- `npm run format:check` (report pre-existing formatting drift honestly)

Cross-layer:

- `python scripts/ci/contract_diff.py`
- `python scripts/ci/docs_api_consistency.py`
- any existing secret/env/schema consistency scripts that can run without unavailable infrastructure

### J.2 Gate honesty

- A command not executed is reported `NOT VERIFIED`, never PASS.
- A command that fails for a pre-existing, unrelated artifact is reported as BLOCKED with evidence and is not claimed as Batch 5 failure or success.
- Live DB/Redis/browser checks are reported according to actual execution.

### J.3 Autonomous bug loop

1. Implement the contract exactly.
2. Run focused gates.
3. Run two independent audits (frontend/UI/security and backend/contract/tests).
4. Classify every finding P0–P3 with evidence.
5. Fix in-scope defects; re-run affected gates.
6. Repeat until two consecutive audits both report zero unresolved in-scope P0/P1/P2/P3 defects.
7. Record audit rounds in the implementation report.

---

## K. Documentation and final deliverables

Required final documents:

- `docs/PHASE6_BATCH5_IMPLEMENTATION_PLAN.md` (this file; frozen after gate)
- `docs/PHASE6_BATCH5_IMPLEMENTATION_REPORT.md` — files changed, defects fixed, gates with exact results, audit rounds, limitations
- `docs/PHASE6_BATCH5_SECURITY_REVIEW.md` — RBAC, tenant isolation, flags, keys, rate limits, error handling, disabled states
- `docs/PHASE6_BATCH5_FINAL_ACCEPTANCE_REPORT.md` — evidence-based statuses using only PASS / FAIL / NOT VERIFIED / BLOCKED / REQUIRES FOUNDER DECISION

Also update:

- `docs/api/endpoints/ai.md`
- `docs/database.md`

Final founder report must not use success language for anything not executed.

---

## L. Acceptance checklist and plan freeze

### L.1 Acceptance checklist

- [ ] Independent plan quality gate passed (17/17) and result appended here.
- [ ] `GET /api/v1/ai/capabilities` exists, is authenticated, org-derived, non-secret, rate-limited, and documented.
- [ ] Malformed per-org `settings.ai` fails closed in `AIService.is_ai_enabled()` with a regression test.
- [ ] `/ai` gated by `ai_run`; Cancel gated by `agent_manage`.
- [ ] `/ai/settings` keeps `ai_manage` and shows truthful capability notices.
- [ ] `/founder` gated by `founder_read`; send/delete/inline decisions gated by `founder_manage`; disabled state when assistant flag/kill switch/budget fails closed.
- [ ] `/founder/proposals` gated by `founder_read`; decisions gated by `founder_manage` and kill switch.
- [ ] `/founder/intelligence` reads available; triage control truthfully disabled when flag off.
- [ ] Frontend service/page tests and backend capability tests added and passing.
- [ ] Two consecutive clean audits with zero unresolved in-scope P0/P1/P2/P3 defects.
- [ ] All applicable gates executed or honestly reported NOT VERIFIED/BLOCKED.
- [ ] Four required final reports written.
- [ ] Protected `0016` untouched; all user-owned artifacts preserved; no staging/commit/push/merge/deploy/PR/main/Batch 6/7 changes.

### L.2 Independent 17-check plan quality gate

**Result: PASS (17/17)** — independent read-only gate completed 2026-11-21.

- First run: FAIL (16/17) — §F.4 conflated a missing `ai` key with malformed `ai` data and would have disabled AI for every new org. Corrected by splitting the branches.
- Final run: PASS (17/17) — all checks passed, including verification of §F.4, the `canView` definition in §G.2, the unified error-envelope reference in §I, and the concrete B5-T-01 service-test list.
- No required corrections remain.

### L.3 Freeze status

**FROZEN — `B5-PLAN-v1.0` is the execution contract for this run. No scope expansion without a new evidence-based amendment.**
