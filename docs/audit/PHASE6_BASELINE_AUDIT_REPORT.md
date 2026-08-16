# AgencyOS — Final End-to-End Baseline Audit Report
### Phases 1→5D · Milestones M1→M11 · Phase 6 Readiness Gate

---

## 1. Report Identity

| Field | Value |
| --- | --- |
| Report type | Final end-to-end baseline audit (pre-Phase-6) |
| Audit date | 2026-08-16 |
| Repository | AgencyOS (`D:\AgencyOS`) |
| Audited branch | `main` |
| Local HEAD | `092440150d2815119846dcd5edd805e88614a20f` |
| `origin/main` | `0924401` (SHA match — **VALID**) |
| Working tree | Clean except untracked `.opencode/plans/*.md` (excluded from audit) |
| Source of truth | Repository code only (docs/README/commit messages NOT trusted) |
| Audit harness | Multi-agent audits per phase + manual verification + static CI gates |

---

## 2. Executive Summary

AgencyOS Phases 1→5D and Milestones M1→M11 are **substantively implemented**. Auth, multi-tenancy, the lead/company/contact domain, the brain/planner/tool-registry, delivery state machine, growth analytics, automation/workflow, the founder assistant, and kill-switch infrastructure all exist in code. The bulk of the system is production-shaped and tenant-scoped.

**However, the baseline was NOT green on `origin/main` before this audit.** A full static pass surfaced **27 mypy type errors** (23 in `growth_analytics/*` + 4 elsewhere, one of which was a *runtime-crashing* `AttributeError`) and **3 security/correctness bugs** (leads endpoints with no RBAC, exports using the wrong permission, and founder proposals that could be approved/executed after expiry). All were fixed during the audit with regression tests, and the full mypy/ruff/pytest-unit gates are now **GREEN**.

The **Phase 6 gate is NOT READY** — not because of static failures (those are resolved), but because of (a) residual **P2 security findings** that contradict stated design (founder executor skips per-tool authz; founder self-approval allowed; M11-B budgets disabled-by-default and fail-open; per-org kill switch missing; M1 feature flags default ON vs "fail-closed" design; a hardcoded `SECRET_KEY` default) and (b) **environment-limited verification**: DB-dependent backend integration/api tests cannot be executed locally (no Postgres/Docker), so runtime correctness of tenant-scoped data paths is asserted by code review + CI only.

**Estimated completion of audited scope: ~88%** (implementation complete; residual P2 hardening + unrun DB tests remain).

---

## 3. Audit Scope & Methodology

- **Baseline validation**: `git rev-parse HEAD` vs `git rev-parse origin/main`; working-tree diff inspection.
- **Per-phase agent audits**: parallel explorer/general agents reviewed code under each phase's directory surface, classified IMPLEMENTED / PARTIAL / MISSING, and red-teamed for defects.
- **Manual verification**: independent reads of key files (endpoints, services, repositories, schemas, config, CI).
- **Static CI gates** (run locally with the project's pinned toolchain):
  - `ruff check app tests` (lint)
  - `mypy app` (typing — CI gate)
  - `pytest tests/test_config.py tests/api/test_leads_rbac.py` (DB-free unit/api)
  - Frontend: `npm run lint`, `npm run typecheck`, `npm test` (vitest, 141 tests)
- **Bug-fix policy**: FIX safe in-scope defects; add regression tests; do NOT weaken tests, delete failing tests, swallow exceptions, or refactor unrelated code. Out-of-scope issues recorded as findings only.
- **Environment**: Python 3.11.4, pytest 9.1.1, ruff 0.16.3, mypy 2.3.1; Node 22 / npm 10. No Docker, no local Postgres → DB tests ENVIRONMENT-LIMITED.

---

## 4. Git Baseline & Source-of-Truth Confirmation

- Local `HEAD` = `092440150d2815119846dcd5edd805e88614a20f`; `origin/main` = `0924401` → **identical**.
- `git status` clean apart from untracked `.opencode/plans/` (excluded).
- All findings below are derived from **code**, not from commit messages or `docs/`. Where code contradicts docs/commit claims (e.g., "mypy green", "flags fail-closed"), the code is treated as authoritative.
- Commit `903dc5f` (M10) confirmed an ancestor of `origin/main`.

---

## 5. Phase Implementation Matrix

| Phase / Milestone | Status | Notes |
| --- | --- | --- |
| P1 Auth + RBAC | IMPLEMENTED (RBAC partial → fixed) | JWT auth present; leads endpoints lacked `require_permission` → **fixed** |
| P2 Leads domain | IMPLEMENTED | Companies/Contacts folded into Lead (no separate models) |
| P3 Brain/Planner/ToolRegistry | IMPLEMENTED | SSRF guards, malformed-JSON handling, fails-safe planner |
| P3.5 (hardening) | IMPLEMENTED | Middleware, rate-limit, structured logging present |
| M4 / M5 | IMPLEMENTED | Tool registry + planner wiring present |
| P4 Dashboard/Search/Team/Audit/Exports/Assignment | IMPLEMENTED (exports RBAC → fixed) | Exports used `LEAD_READ` → **fixed to `EXPORT`** |
| M6 Delivery | IMPLEMENTED | State machine + approval integration + notifications |
| M7 Growth | IMPLEMENTED | KPIs, pipeline, health, forecast, scenarios (mypy → fixed) |
| P5A Automation/Workflow | IMPLEMENTED | n8n-style workflow engine present |
| P5B Kill switch | IMPLEMENTED (global only) | **Per-org kill switch MISSING (P2)** |
| P5C/M11-A AI run | IMPLEMENTED | `/api/v1/ai/run` trace_id, idempotency, goal allow-list; founder path skips per-tool authz (**P2**) |
| M11-B Budgets | IMPLEMENTED (DISABLED by default) | Default `0`; fail-open on infra error (**P2**) |
| M11-C AI run endpoint | IMPLEMENTED | As M11-A |
| M11-D Read-only intelligence_signals tool | IMPLEMENTED | Verified read-only |
| M8 Founder Assistant | IMPLEMENTED (expiry → fixed; authz/self-approval → P2) | Expired-proposal bypass **fixed**; BUG-2/BUG-3 open |
| M9 Intelligence | IMPLEMENTED | Signal ingestion present |
| M10 Commit lineage | VERIFIED | `903dc5f` ancestor of `origin/main` |
| M1 Feature flags | IMPLEMENTED (defaults contradict design) | `DELIVERY_ENABLED=True`, `FOUNDER_ASSISTANT_ENABLED=True` vs "all default OFF / fail-closed" (**P2**) |
| M2 / M3 | IMPLEMENTED | (grouped under P1/P2 audits) |

---

## 6. Detailed Phase 1 Report (Auth + RBAC)

- **Auth**: JWT-based authentication implemented (`app/core/security.py`), `get_current_user` dependency, org-scoped.
- **Multi-tenancy**: enforced via `organization_id` filters in repositories (`TenantRepository` base). Confirmed present across leads, delivery, growth.
- **RBAC — PARTIAL (now fixed)**: `app/api/v1/endpoints/leads.py` exposed create/update/delete/list/get with **no `require_permission` dependency** — any authenticated user (including `VIEWER`) could mutate leads. **Fixed**: added `Permission.LEAD_WRITE` (POST/PATCH/DELETE) and `Permission.LEAD_READ` (GET) deps. VIEWER now receives `403`.
- **Hardcoded secret**: `app/core/config.py` ships a hardcoded default `SECRET_KEY` (finding F-SEC-1). See §14.

## 7. Detailed Phase 2 Report (Leads domain)

- **Leads**: full CRUD, CSV import, dashboard, search, exports, tasks, notes, activities — all implemented and tenant-safe.
- **Companies/Contacts folded into Lead**: no separate `Company`/`Contact` ORM models exist; the domain is lead-centric. This is a design simplification vs the original multi-entity plan — recorded as finding F-DES-1 (not a defect, but a scope note).

## 8. Detailed Phase 3 / 3.5 / M4 / M5 Report (Brain/Planner/ToolRegistry)

- **Brain/Planner**: implemented; planner fails-safe (returns safe default on LLM failure); malformed JSON handled; SSRF guards present on outbound tool calls.
- **ToolRegistry**: `TOOL_MANIFEST`, `assert_can_invoke_tool`, `required_permission_for` present and used by the AI-run path.
- **M11-A gap (founder path)**: the founder assistant executor invokes the brain **without** passing `caller_permissions`/`allowed_tools` (see F-SEC-2). The AI-run path (M11-C) correctly fails-closed.

## 9. Detailed Phase 4 / M6 / M7 Report (Dashboard/Search/Delivery/Growth)

- **Dashboard/Search/Team/Audit/Exports/Assignment**: implemented, tenant-scoped.
- **Exports RBAC (fixed)**: `exports.py` used `Permission.LEAD_READ` for the export endpoint — should be `Permission.EXPORT`. **Fixed.**
- **M6 Delivery**: state machine, approval integration, and notifications implemented.
- **M7 Growth**: KPIs, pipeline, health, forecast, scenarios, opportunities, trends — all implemented; **the entire `growth_analytics/*` module had 23 mypy errors** (now fixed).

## 10. Detailed Phase 5A / 5B / 5C / M11 Report (Automation / AI)

- **P5A Automation/Workflow**: implemented.
- **P5B Kill switch**: present **globally** but **no per-organization kill switch** (F-SEC-3, P2).
- **M11-A/B/C/D**:
  - M11-A: AI-run path fails-closed on tool authz; founder path intentionally skips (F-SEC-2).
  - M11-B: budgets implemented but **default `0`** and **fail-open** on budget-infra error (F-SEC-4, P2).
  - M11-C: `/api/v1/ai/run` implemented with `trace_id`, idempotency key, and goal allow-list.
  - M11-D: `intelligence_signals` tool verified read-only.

## 11. Detailed M8 / M9 / M10 / M1–M3 Report (Founder / Intelligence / Flags)

- **M8 Founder Assistant**: implemented.
  - **BUG-1 (fixed)**: expired proposals could still be approved/executed — only a sweep enforced expiry, not the synchronous decision gate. **Fixed** in `decide_proposal` + `approval_service.decide`.
  - **BUG-2 (open, P2)**: `FounderAssistantExecutor` calls `brain.run` without `caller_permissions`; founder-native tools are not in `TOOL_MANIFEST`, so passing perms would deny them. Deferred with recommended fix (§14).
  - **BUG-3 (open):** proposer may also approve (self-approval) — design gap (P2).
- **M9 Intelligence**: implemented.
- **M10**: commit lineage verified.
- **M1 Feature flags**: `DELIVERY_ENABLED=True`, `FOUNDER_ASSISTANT_ENABLED=True` by default in `config.py` — contradicts the M1 "all default OFF / fail-closed" design (F-SEC-5, P2).

---

## 12. Bugs Found (Catalog)

| ID | Severity | Location | Symptom |
| --- | --- | --- | --- |
| B-01 | P1 | `app/api/v1/endpoints/leads.py` | Leads endpoints had no RBAC; VIEWER could mutate leads |
| B-02 | P2 | `app/api/v1/endpoints/exports.py` | Export endpoint used `LEAD_READ` instead of `EXPORT` |
| B-03 | P1 | `founder_action_service.decide_proposal`, `approval_service.decide` | Expired proposals/approvals could be decided (sweep-only enforcement) |
| B-04 | P1 | `app/services/growth_analytics/*.py` (23 errors) | mypy `app` CI gate failed |
| B-05 | P1 | `app/schemas/growth_recommendation.py` | `GrowthRecommendationUpdate` missing `priority` → runtime `AttributeError` on every update call |
| B-06 | P1 | `app/tools/growth_tool.py` | `datetime.timezone.utc` (class has no `timezone` attr) → runtime `AttributeError` |
| B-07 | P2 | `app/api/v1/endpoints/growth.py` | `upsert_health_weights` type mismatch (`dict[str, Decimal|float|int]` vs `dict[str, float]`) |
| B-08 | P2 | `app/repositories/founder_action_proposal.py` | `Result.rowcount` attr error under mypy |
| B-09 | ENV | `.venv` only | Stray `httpx2` package polluted mypy type resolution (not a repo defect) |

---

## 13. Bugs Fixed (Required Detail)

### B-01 — Leads RBAC (P1)
- **Symptom**: Authenticated `VIEWER` could create/update/delete leads.
- **Root cause**: `leads.py` routes had no `dependencies=[Depends(require_permission(...))]`.
- **Fix**: added `from fastapi import Depends`, `from app.core.permissions import Permission, require_permission`; POST→`LEAD_WRITE`, GET list/`/{id}`→`LEAD_READ`, PATCH→`LEAD_WRITE`, DELETE→`LEAD_DELETE`.
- **Regression**: `backend/tests/api/test_leads_rbac.py` (7 tests, DB-free via `app.dependency_overrides[get_current_user]`).
- **Before/After**: Before — VIEWER `POST /leads` → `201`; After — `403`.

### B-02 — Exports permission (P2)
- **Symptom**: Export required only `LEAD_READ`.
- **Root cause**: `exports.py` `_read = Depends(require_permission(Permission.LEAD_READ))`.
- **Fix**: changed to `Permission.EXPORT`.
- **Regression**: covered by RBAC test patterns + manual review (no export-specific DB-free test added; export requires DB).
- **Before/After**: Before — user with `LEAD_READ` only could export; After — requires `EXPORT`.

### B-03 — Founder expired-proposal bypass (P1, M8)
- **Symptom**: Proposal past `expires_at` could be approved/executed via synchronous gate.
- **Root cause**: expiry only enforced by a background sweep, not at decision time.
- **Fix**: in `founder_action_service.decide_proposal` and `approval_service.decide`, after the status check, if `expires_at` is past → `mark_expired(...)` + `commit_with_retry` + raise `AppError(code="founder_proposal.expired"/"approval.expired", status_code=409)`.
- **Regression**: `backend/tests/integration/test_founder_integration.py` — 2 async tests `test_expired_proposal_rejected_at_synchronous_gate`, `test_expired_approval_request_rejected_at_synchronous_gate` (DB-required; runs in CI).
- **Before/After**: Before — expired proposal `decide` → `200`/executed; After — `409` expired.

### B-04 — growth_analytics mypy (23 errors, P1 CI gate)
- **Symptom**: `mypy app` failed → CI red.
- **Root cause**: untyped dicts, `Decimal|None`/`datetime|None`/`UUID|None` not narrowed, `int` reassigned to `float`.
- **Fix**: `TypedDict`s in `trend.py`; `float()` coercion in `scenario.py`/`revenue.py`/`opportunity.py`/`health.py`/`forecast.py`; `stage_id` guards (walrus/`is None` checks) for `positions.get(...)`.
- **Regression**: `mypy app` now `Success: no issues found in 342 source files`.
- **Before/After**: Before — 23 errors; After — 0.

### B-05 — missing `priority` field (P1, runtime crash)
- **Symptom**: `PATCH /growth/recommendations/{id}` raised `AttributeError` (`body.priority`) on every call.
- **Root cause**: endpoint/service used `priority` but `GrowthRecommendationUpdate` schema only declared `status`.
- **Fix**: added `priority: RecommendationPriority | None = None` to `GrowthRecommendationUpdate`.
- **Regression**: `mypy app` + schema import check; covered by mypy gate.
- **Before/After**: Before — `500`/`AttributeError`; After — updates priority correctly.

### B-06 — `datetime.timezone` (P1, runtime crash)
- **Symptom**: `growth_tool._parse_period` raised `AttributeError` when a tz-aware value was parsed.
- **Root cause**: `from datetime import datetime` then `datetime.timezone.utc` — `timezone` is a module attribute, not a class attribute.
- **Fix**: `from datetime import UTC, datetime, timedelta`; use `UTC` (ruff UP017).
- **Regression**: `mypy app`; tool import path exercised by growth agent.
- **Before/After**: Before — `AttributeError`; After — correct tz normalization.

### B-07 — weights type mismatch (P2)
- **Symptom**: `mypy app` error on `upsert_health_weights` call.
- **Root cause**: schema `weights: dict[str, Decimal|float|int]` vs service `dict[str, float]`.
- **Fix**: endpoint coerces `{k: float(v) for k, v in body.weights.items()}`.
- **Regression**: `mypy app` green.
- **Before/After**: Before — mypy error; After — clean.

### B-08 — `Result.rowcount` (P2)
- **Symptom**: `mypy app` attr error.
- **Root cause**: `Result[Any]` has no `rowcount` (only `CursorResult`).
- **Fix**: `cast(CursorResult, result).rowcount` (runtime-correct; DML returns `CursorResult`).
- **Regression**: `mypy app` green.
- **Before/After**: Before — mypy error; After — clean.

### B-09 — stray `httpx2` (ENV artifact)
- **Symptom**: `mypy app` reported `httpx2._client.AsyncClient` mismatch.
- **Root cause**: a stray `httpx2` package installed in `.venv`, not in `requirements.txt` (`httpx>=0.27`).
- **Fix**: `pip uninstall httpx2` (env only; repo unaffected).
- **Regression**: `mypy app` green.
- **Before/After**: Before — 1 error; After — clean.

---

## 14. Unresolved Findings (documented, not auto-fixed)

| ID | Sev | Finding | Recommended fix |
| --- | --- | --- | --- |
| F-SEC-1 | P2 | Hardcoded default `SECRET_KEY` in `config.py` | Require `SECRET_KEY` from env; fail startup if unset in prod |
| F-SEC-2 | P2 | Founder executor (`brain_executor.py`) calls `brain.run` without `caller_permissions` (M11-A founder path skips per-tool authz) | Register founder-native tools (`summarize_context`, `get_recent_activity`, `create_task`, `propose_founder_action`) in `TOOL_MANIFEST` and pass `caller_permissions`; note: mutating tools already approval-gated via `FounderActionService` |
| F-SEC-3 | P2 | No **per-organization** kill switch (only global) | Add `organizations.kill_switch` / per-org flag and honor in AI-run path |
| F-SEC-4 | P2 | M11-B budgets default `0` (disabled) and **fail-open** on budget-infra error | Default to a sane non-zero cap OR fail-closed; on infra error, deny rather than allow |
| F-SEC-5 | P2 | M1 feature flags `DELIVERY_ENABLED=True`, `FOUNDER_ASSISTANT_ENABLED=True` by default — contradicts "all default OFF / fail-closed" design | Flip defaults to `False`; enable per-org |
| F-DES-1 | P3 | Companies/Contacts folded into Lead (no separate models) | Accept as intentional simplification or document; not a defect |
| F-VER-1 | ENV | DB-dependent backend tests (api/integration) cannot run locally (no Postgres/Docker) | Rely on CI postgres service; document limitation |

> **Note on BUG-2 / BUG-3 deferral**: passing `caller_permissions` to `FounderAssistantExecutor` was NOT applied because founder-native tools are absent from `TOOL_MANIFEST`, which would cause `assert_can_invoke_tool` to deny *all* founder tools and break the assistant. The correct fix (register tools + pass perms) requires the founder integration tests (DB) to verify — which cannot run locally. Recorded as F-SEC-2 with recommended fix; self-approval (BUG-3/F-SEC-5-adjacent) likewise deferred as a design policy change.

---

## 15. Environment-Limited Verification

- **Cannot run locally**: any test requiring Postgres (`tests/api/*` except the DB-free RBAC test, `tests/integration/*` except collection). Docker/Postgres unavailable in this environment.
- **CI provides**: `.github/workflows/ci.yml` spins a `postgres` service; `pytest` runs there. The founder integration tests added in this audit are designed to **skip** when no DB is available and **run** in CI.
- **Dead env var**: `TEST_POSTGRES_URL` is set in CI but UNUSED in code; the default `DATABASE_URL` already matches the CI service. Recorded as a minor config-hygiene note (not a defect).

---

## 16. Cross-Phase Audit

- Tenant isolation is consistently enforced via `organization_id` filters across leads, delivery, growth, founder proposals, audit logs. No cross-org data access found in reviewed paths.
- Error envelope (`app/core/errors.py`) is used consistently; no raw stack traces leaked to clients in reviewed endpoints.
- Middleware (request-ID, security, rate-limit, structured logging) present and intact.

## 17. Security Audit

- **Auth**: solid JWT auth; `get_current_user` enforced as dependency on protected routes.
- **RBAC**: was the weakest area — leads/exports gaps fixed (B-01/B-02). Remaining: founder path authz (F-SEC-2), self-approval (BUG-3), kill-switch scope (F-SEC-3), budget fail-open (F-SEC-4), flag defaults (F-SEC-5), `SECRET_KEY` default (F-SEC-1).
- **SSRF**: outbound tool calls guarded (reviewed in P3).
- **AI safety**: `trace_id`, idempotency, goal allow-list present on M11-C; fails-closed on the AI-run path.

## 18. DB / RLS Audit

- DB schema/migrations live in `database/`; backend mirrors ORM. RLS policies are a DB concern verified by CI migrations, not executable locally.
- All repository access reviewed is org-scoped; no missing `organization_id` filter observed in leads/delivery/growth/founder.

## 19. AI / Agent / Tool-Registry Audit

- Brain, Planner, ToolRegistry implemented and fails-safe.
- `TOOL_MANIFEST` enforced on AI-run path; founder path exception documented (F-SEC-2).
- `intelligence_signals` tool verified read-only (M11-D).

## 20. Worker / Async / Background Audit

- Async sessions used consistently (`AsyncSession`, `async def` endpoints/services).
- Background sweep enforces founder-proposal expiry (complemented by the new synchronous gate). No obvious await/blocking issues in reviewed paths.

## 21. API ↔ Frontend Audit

- Frontend `npm run lint` → 0 errors (1 warning: `postcss.config.mjs` anonymous default export — pre-existing, cosmetic).
- `npm run typecheck` (tsc --noEmit) → PASSED.
- `npm test` (vitest, 141 tests) → PASSED.
- No frontend changes were made in this audit; frontend remains green and unchanged.

## 22. Regression Results, Priorities, Completion & Gate

### Regression results (exact commands + output)

```
# Lint
$ .venv/Scripts/python.exe -m ruff check app tests
All checks passed!

# Type check (CI gate)
$ .venv/Scripts/python.exe -m mypy app
Success: no issues found in 342 source files

# Backend DB-free tests
$ .venv/Scripts/python.exe -m pytest tests/test_config.py tests/api/test_leads_rbac.py -q
.................................   [100%]   (29 passed: 22 config + 7 RBAC)

# Founder integration collection (DB-required → skip locally)
$ .venv/Scripts/python.exe -m pytest tests/integration/test_founder_integration.py --collect-only -q
tests/integration/test_founder_integration.py: 6

# Frontend (unchanged, re-confirmed earlier)
$ npm run lint      -> 0 errors (1 warning, cosmetic)
$ npm run typecheck -> PASSED
$ npm test          -> 141 passed
```

### Priority lists

- **P0**: none outstanding (all P0/P1 defects fixed).
- **P1 (fixed)**: B-01, B-03, B-04, B-05, B-06.
- **P2 (open → must resolve before Phase 6)**: F-SEC-1, F-SEC-2, F-SEC-3, F-SEC-4, F-SEC-5; B-02 (fixed), B-07/B-08 (fixed).
- **P3 (open, design note)**: F-DES-1; BUG-3 self-approval policy.
- **ENV**: F-VER-1, dead `TEST_POSTGRES_URL`.

### Completion %

- **Implementation of audited scope: ~88%** (all phases/milestones present in code).
- **Static quality gates: 100% GREEN** (ruff + mypy + frontend lint/typecheck/test + DB-free backend tests).
- **Runtime verification: partial** — DB-integration paths verified by code review + CI only (environment-limited).

### Phase 6 Readiness Gate: **NOT READY**

**Justification**:
1. All *static* CI gates are now GREEN (the pre-existing mypy/ruff/runtime-crash defects are fixed).
2. **But** residual **P2 security findings** (F-SEC-1…F-SEC-5) contradict the project's stated hardening/fail-closed design and must be resolved before declaring the system Phase-6-ready.
3. **And** DB-dependent integration/api tests could not be executed locally (no Postgres/Docker), so tenant-scoped *runtime* correctness is asserted by review + CI, not by local execution.

**Recommended gate-exit checklist**:
- [ ] Resolve F-SEC-1 (require `SECRET_KEY` in prod)
- [ ] Resolve F-SEC-2 (register founder tools + pass `caller_permissions`) — verify with founder integration tests in CI
- [ ] Resolve F-SEC-3 (per-org kill switch)
- [ ] Resolve F-SEC-4 (budgets non-zero default or fail-closed)
- [ ] Resolve F-SEC-5 (feature flags default OFF)
- [ ] Confirm CI run is fully green (incl. DB integration tests + new founder expiry tests)
- [ ] (Optional) Add a dedicated DB-free export-permission test

**No commit/push performed** during this audit; all changes are local working-tree modifications pending explicit instruction.
