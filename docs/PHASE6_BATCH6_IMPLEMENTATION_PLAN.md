# AgencyOS Phase 6 — Batch 6 (Automation) Implementation Plan

**Document:** `docs/PHASE6_BATCH6_IMPLEMENTATION_PLAN.md`  
**Plan version:** `B6-PLAN-v1.0`  
**Mode:** PLAN → EXECUTE (same authorized run); no commit, push, merge, deploy, PR change, or `main` change  
**Branch:** `feat/phase6-commercial-v1`  
**Baseline HEAD:** `7f53ffaa5456b7ef7d1f58d8a441c086bf05fac0` (local and upstream)  
**Baseline main:** `ba33074fe8bbcc43382bc0a7d77d24ce682c7cec` (not modified)  
**Date:** 2026-11-21  
**Status:** DRAFT — pending independent 17-check plan quality gate; execution is not authorized until the gate result is appended in §S and §T is updated to FROZEN.

---

## A. Executive summary

Batch 6 is exactly the six canonical Automation routes in the Commercial V1 inventory:

1. `/workflows`
2. `/workflows/[id]`
3. `/triggers`
4. `/executions`
5. `/credentials`
6. `/deliveries`

This is a **verification + hardening + extension** batch, not a greenfield build. Phase 5A–D already delivered the backend workflow/trigger/execution engine, queue drain, builtin execution engine, n8n adapter, credentials vault, delivery outbox, scheduler, worker health, kill switch, audit events, timeline, RLS, and monitoring endpoints. Batch 4 delivered the permission/denied/error-state patterns. Batch 5 delivered fail-closed capability helpers, typed permission helpers, and truthful-disabled patterns. Batch 6 must reuse all of it.

The canonical design requires read-only workflow visualization, no visual builder, no invented routes, no fake success, no arbitrary workflow code execution, no live provider calls, and truthful unavailable/unauthorized states. Backend permissions remain authoritative. The frontend is UX-only.

The principal in-scope corrections are:

- Align frontend automation permission keys with the actual backend permission constants.
- Add explicit read-denied, loading, empty, error+retry, and state-dependent action states to all six routes.
- Add the missing read-only flow visualization, Run now, config/action detail, trigger create/edit, execution detail/timeline, and delivery summary/detail fields **inside** existing canonical routes.
- Keep credentials admin-only and write-only; do not claim browser-side plaintext secret encryption that does not exist.
- Harden inbound/outbound webhook authenticity, replay handling, n8n webhook path validation, signing, org scoping, idempotency metadata, and bounded failure behavior.
- Redact raw delivery/provider metadata and never display secrets, hostnames, tokens, payloads, or cross-tenant data.
- Add unit, service, SSR/markup, API, security, and role-matrix regression tests.
- Run current Batch 6 gates only; never reuse Batch 5 or old CI results as Batch 6 evidence.

No new schema, migration, RLS policy, dependency, generic workflow code execution, live SMTP/WhatsApp/calendar call, paid AI call, or product/architecture decision is authorized by this plan.

---

## B. Verified baseline and preservation constraints

Verified locally at plan start:

| Check | Evidence | Result |
|---|---|---|
| Branch | `git status --short --branch` | `feat/phase6-commercial-v1` |
| HEAD | `git rev-parse HEAD` | `7f53ffaa5456b7ef7d1f58d8a441c086bf05fac0` |
| Upstream branch | `git rev-parse origin/feat/phase6-commercial-v1` | same as HEAD |
| `main` | `git rev-parse main` | `ba33074fe8bbcc43382bc0a7d77d24ce682c7cec` |
| Staging | `git diff --cached --name-only` | empty |
| Protected `0016` migration | present as pre-existing modified artifact | must never be opened, read, inspected, diffed, hashed, staged, modified, renamed, or deleted |

Preservation rules:

- All Batch 5 modified/untracked files are baseline artifacts and must remain byte-preserved except where Batch 6 explicitly hardens them.
- All other pre-existing untracked artifacts — including planning docs, PDFs, logs, CSV uploads, `.opencode`, `opencode.jsonc`, and frontend `AGENTS.md` — are user-owned and must not be deleted or overwritten.
- No `git add`, `git add .`, `git add -A`, commit, push, force-push, merge, reset, clean, stash, checkout of user files, deploy, PR change, `main` change, or Batch 7 work.
- No dependency install/upgrade, lockfile change, CI config change, or production config change outside the evidence-driven env-template documentation.

Baseline inventory was captured with `git status --porcelain=v1 --untracked-files=all`. It includes Batch 5 source/tests/docs and user artifacts; the protected migration remains untouched.

Environment observations:

- `psql`, `docker`, `redis-cli`, and `gh` are not available in PATH.
- Backend virtualenv Python is available at `backend\.venv\Scripts\python.exe` (3.14.6).
- Local DB/Redis-dependent tests will be reported as skipped with exact reasons, never counted as passing.
- Historical CI run `#74` is Batch 5 evidence only and is not reused here.

---

## C. Canonical sources inspected

Sources used to freeze this contract:

| Source | Use |
|---|---|
| `docs/PHASE6_COMMERCIAL_V1_IMPLEMENTATION_PLAN.md` | Numeric batch 6 = Automation; no fake success; credentials admin-only/write-only |
| `AGENCYOS_PHASE6_MASTER_IMPLEMENTATION_BLUEPRINT.md` | 37-route inventory; rows 30–35; read-only flow visualization; no invented routes/statuses |
| `docs/AGENCYOS_PHASE6_EXECUTION_PLAN.md` | Batch F maps to Automation; test-layer expectations |
| `docs/AGENCYOS_PHASE6_DECISION_REGISTER.md` | D-01…D-18; D-02, D-12, D-13, D-18 constraints |
| `docs/AGENCYOS_PHASE6_BACKEND_COMPATIBILITY_AUDIT.md` | Routes 30–35 backend readiness; permission split |
| `docs/AGENCYOS_COMPLETE_FRONTEND_INFORMATION_ARCHITECTURE_DRAFT.md` | Automation screen catalog |
| `docs/AGENCYOS_ALL_IN_ONE.pdf` | Approved design reference; extracted text for screens 24–28 and route coverage |
| `docs/phase6/PHASE6_IMPLEMENTATION_STRUCTURE_AND_PLAN.md` | Batch F mapping; honest unavailable states |
| `docs/phase5a-report.md`, `docs/phase5b-report.md`, `docs/phase5c-final-report.md`, `docs/M10-FINDINGS.md` | Existing automation foundations to reuse |
| `docs/PHASE6_BATCH4_IMPLEMENTATION_PLAN.md` | Monitoring denied/error-state pattern |
| `docs/PHASE6_BATCH5_*` | Frozen predecessor contract, capability/permission patterns, decisions |
| `backend/app/**` | Actual endpoint, service, repository, model, worker, permissions, config reality |
| `frontend/src/**` | Actual routes, services, types, permission helpers, tests |
| `.github/workflows/ci.yml` | Current enforced gates |
| `AGENTS.md`, `frontend/AGENTS.md`, installed Next.js docs | Repository and framework rules |

Contradictions resolved:

- The older Readiness Baseline defines a different AI-brain Phase 6; the Commercial V1/Blueprint lineage governs Batch 6.
- Automation is “Batch F” in lettered plans and “Batch 6” in numeric plans; both mean the same six routes.
- “Batch F already implemented” means existing foundations exist; it does not mean Batch 6 is complete. Current code audit found real defects.
- D-13 is implemented in Batch 5; the decision register is stale. Do not reopen it.
- D-02 and D-18 remain founder decisions; preserve Batch 5 behavior and do not make the decision for the founder.
- No live n8n/SMTP/WhatsApp/calendar integration is authorized. Readiness docs saying these are goals are superseded by integration-readiness evidence that they are unconfigured/deferred.

---

## D. Exact scope, route and screen inventory

### D.1 Canonical routes — fixed

| # | Route | Batch 6 behavior | Backend authority | Class |
|---:|---|---|---|---|
| 30 | `/workflows` | Workflow list, status filter, create/edit, authorized transitions, truthful states | `WORKFLOW_READ/WRITE/MANAGE`; nav `AUTOMATION_READ` | HARDEN |
| 31 | `/workflows/[id]` | Metadata, triggers, recent executions, read-only flow visualization, config/action detail, Run now, authorized transitions | `WORKFLOW_READ/WRITE/MANAGE`, `AUTOMATION_*`, `EXECUTION_*` | EXTEND |
| 32 | `/triggers` | Org-wide trigger table, supported types, create/edit drawer, enabled state, last-triggered visibility | `AUTOMATION_READ/WRITE/MANAGE` | EXTEND |
| 33 | `/executions` | Metrics, filters, table, duration, detail/timeline, error summary, authorized retry/cancel | `EXECUTION_READ`, write via `WORKFLOW_WRITE`, events endpoint | EXTEND |
| 34 | `/credentials` | Admin-only list and create/replace UI; write-only secrets; never show values again | all endpoints `CREDENTIAL_MANAGE` | HARDEN |
| 35 | `/deliveries` | Metrics, table, attempt history, redacted timeline, authorized retry/cancel; no fake destination | `DELIVERY_READ/WRITE/MANAGE` | HARDEN |

### D.2 Explicitly not Batch 6

No new canonical routes. Specifically excluded:

- `/executions/[id]`, `/deliveries/[id]`, `/triggers/new`, `/credentials/[id]`, `/workflow-events`, `/logs`.
- `/monitoring`, `/assignment`, `/worker-monitoring`, `/operational-monitoring`, `/settings/security`.
- Workflow visual builder, arbitrary action code, unsupported trigger/action/condition nodes.
- Batch 7 brand/3D work, Core Orbit asset changes, billing, developer portal, public chatbot, generic approvals, memory, task board, appearance persistence, mark-all-read.
- Contact/Demo submission backends, live provider integrations, live AI calls.

### D.3 Screen-level inventory

| Route | Required surfaces | Current gap | Batch 6 action |
|---|---|---|---|
| `/workflows` | loading/empty/error+retry/read-denied, create, edit, activate/pause/archive/delete | no denied/retry/edit; permission drift | HARDEN + EXTEND |
| `/workflows/[id]` | breadcrumb/status, read-only node flow, trigger table, config/action detail, recent executions, Run now, edit, transitions | no flow, no Run now, no config detail, no edit; drift | EXTEND |
| `/triggers` | table, type/workflow filters, enabled state, last triggered, create/edit, denied/retry | no create/edit/last-triggered; client-only filter; drift | EXTEND |
| `/executions` | summary cards, filters, duration, detail/timeline, error summary, retry/cancel | no cards/detail/timeline/error; no events wrapper | EXTEND |
| `/credentials` | admin-only list, create/replace, status/updated, write-only warning, denied/retry | broader FE gates; no denied/retry; questionable plaintext form | HARDEN |
| `/deliveries` | summary cards, ID/event/status/attempts/last attempt, redacted timeline, retry/cancel | no cards/columns; raw metadata JSON rendered | HARDEN + EXTEND |

---

## E. Endpoint and capability classification

### E.1 Endpoint matrix

| Surface | Existing endpoint/service | Permission | Batch 6 use |
|---|---|---|---|
| Workflow list/get/create/update | `/api/v1/workflows*`; `frontend/src/services/workflows.ts` | `WORKFLOW_READ/WRITE/MANAGE` | REUSE; add UI for existing `updateWorkflow` |
| Workflow transitions | activate/pause/archive/delete | `WORKFLOW_MANAGE` | REUSE; state/permission conditional |
| Workflow detail data | `getWorkflow`, triggers, executions | respective read perms | REUSE |
| Run now | `POST /workflow-executions`; `queueWorkflowExecution` | `EXECUTION_*`/workflow permission contract | REUSE; wire existing service |
| Trigger CRUD | `/api/v1/workflow-triggers*` | `AUTOMATION_READ/WRITE/MANAGE` | REUSE; add create/edit UI |
| Execution list/detail/lifecycle | `/api/v1/workflow-executions*` | `EXECUTION_READ`, `WORKFLOW_WRITE` | REUSE; add detail wrapper/timeline |
| Execution events | `GET /workflow-executions/{id}/events` | existing backend read gate | REUSE; add FE wrapper only |
| Credentials | `/api/v1/credentials*` | all `CREDENTIAL_MANAGE` | REUSE; tighten frontend gate |
| Deliveries | `/api/v1/deliveries*`, `/events` | `DELIVERY_READ/WRITE/MANAGE` | REUSE; redact metadata |
| Automation control | `/api/v1/automation-control*` | admin-only `AUTOMATION_CONTROL` | REUSE — no new canonical page |
| Monitoring | `/api/v1/monitoring*` | `AUTOMATION_READ` vs `AUTOMATION_MANAGE` | REUSE pattern only |
| n8n dispatch | `N8nClient`, `N8nTool`, execution adapter | tool registry/AI permissions | HARDEN |
| Inbound webhook | `POST /webhooks/leads` | shared secret | HARDEN |
| Provider health | no endpoint; `N8nClient.health_check()` exists but unwired | none | DEFERRED / REQUIRES FOUNDER DECISION |

### E.2 Capability classification

| Capability | Class | Evidence and Batch 6 treatment |
|---|---|---|
| Workflow/trigger/execution backend engine | REUSE | Phase 5A–C; no rebuild |
| Queue drain, worker health, kill switch, timeline, audit/retention | REUSE | Phase 5C; no rebuild |
| Credential vault, KMS envelope encryption, rotation | REUSE | `credential_service.py`, `core/kms.py`, `core/crypto.py` |
| Delivery outbox and in-app provider | REUSE | `delivery_service.py`, `communication/providers.py` |
| Inbound lead webhook primitive | REUSE | `webhooks.py` shared-secret and idempotency |
| Inbound webhook HMAC/timestamp/nonce/replay | NEW | hardening the existing endpoint with signed headers and a bounded replay guard |
| n8n HTTP transport and tool allow-list | HARDEN | add path validation, signature, org/idempotency metadata, retries |
| AI tool registry / planner allow-lists / kill switch / budgets | REUSE | Batch 5 and M11; never pass `caller_permissions=None` on new paths |
| Founder approval gate | REUSE | no new mutation path |
| Founder `SEND_EMAIL`/`RUN_WORKFLOW`/`EXPORT` execution | FOUNDER DECISION | no subsystem owner found; do not implement |
| SMTP account-security email | REUSE | narrow account-security scope only |
| Email/WhatsApp/push delivery providers | DEFERRED | no provider registered; fail closed |
| Calendar provider/agent | DEFERRED | registry marks Calendar Agent FUTURE |
| Provider/integration health endpoint | DEFERRED | would be NEW if approved; no canonical Batch 6 route, do not add without decision |
| Root/backend env templates | HARDEN | document only required names; no values |

No canonical capability is `COMPLETE` in the frontend today; all six routes require hardening or extension.

---

## F. Backend implementation plan

F.1 **Inbound webhook authenticity**

- Reuse `WEBHOOK_SECRET`; no new inbound signing secret is introduced. Keep the constant-time shared-header check.
- When `WEBHOOK_SECRET` is configured, HMAC-SHA256 signature verification over `timestamp + nonce + raw body` is **mandatory**: missing, malformed, stale, or incorrect signatures are rejected with the unified error envelope.
- Bound timestamp skew with `WEBHOOK_TIMESTAMP_SKEW_SECONDS` (default 300) and require a non-empty 8–128 character nonce.
- Replay guard: in deployed environments (`APP_ENV` not in the explicit local set), use shared Redis (`REDIS_URL`, already mandatory outside local) with key scoped by organization and nonce, `SET NX EX` with `WEBHOOK_REPLAY_TTL_SECONDS` (default 600). Only `development`/`dev`/`local`/`test`/`testing`/`ci` may use a bounded in-process fallback; that fallback is per-process and is never used in production. Replay detection fails closed.
- Preserve the existing idempotent lead response for duplicate payloads.
- Add tests for valid, wrong, missing, stale, replayed, malformed, and unconfigured-secret cases.

F.2 **Outbound n8n hardening**

- Validate `webhook_path` from workflow config: relative path only, must start with `/webhook/`, no scheme, credentials, traversal segments, backslashes, control characters, or query string.
- Keep `N8N_BASE_URL` as the only dispatch authority; never accept a full URL from workflow config.
- Add HMAC-SHA256 signature headers using `N8N_WEBHOOK_SECRET` (new config field plus env-template documentation; no API/schema/storage contract change). When `N8N_BASE_URL` is configured and `settings.is_local_environment` is false, this secret is mandatory: `Settings.validate_runtime()` fails closed in every deployed environment (staging/QA/unknown included). `validate_for_production()` additionally asserts it when `APP_ENV=production`; local tests use an explicit test value.
- Include timestamp, nonce, org id, actor id when available, workflow/execution id, and idempotency key in signed headers/payload metadata.
- Add bounded timeout, limited retries with backoff for transient failures only, and sanitized errors.
- Do not expose keys, host details, or response bodies to clients/logs.
- Add tests for path rejection, signing, retry classification, org metadata, and sanitized diagnostics.

F.3 **Authorization and tenancy**

- Do not remove or broaden any backend permission dependency.
- All data access must remain org-derived from authenticated context; no client-supplied org id authority.
- New code paths must never call tool registry with `caller_permissions=None`.
- Reuse unified error envelope in `app/core/errors.py`; no stack traces to clients.

F.4 **Concrete backend defects to fix in this batch**

| ID | Severity | Evidence | Fix |
|---|---|---|---|
| B6-F-01 | P1 | `backend/app/api/v1/endpoints/workflows.py:95-116`: `GET /{workflow_id}` is declared before `GET /active`, so the literal path can be shadowed | Move the `/active` route above the dynamic route and add a regression test |
| B6-F-02 | P1 | `backend/app/schemas/workflow.py:31`, `backend/app/services/workflow_service.py:153-154`: generic update can set `status` directly | Reject status changes through generic update; require activate/pause/archive endpoints; add regression test |
| B6-F-03 | P1 | `backend/app/api/v1/endpoints/workflows.py:283-318`: nested trigger update/delete ignores path `workflow_id` | Verify the trigger belongs to the path workflow and org before mutation; add regression test |
| B6-F-04 | P1 | `backend/app/api/v1/endpoints/workflow_executions.py:136-153`, `workflow_execution_service.py:236-270`: manual `start` is not kill-switch gated | Call the existing kill-switch guard in `start()`; add regression test |
| B6-F-05 | P1 | `backend/app/services/schedule_dispatcher.py:169-193`, `workflow_execution_service.py:227`: `queue()` commits inside the dispatcher savepoint | Add `commit=False` keyword to `queue()` (default `True` preserves all other callers); dispatcher passes `False`, flushes only inside each savepoint, and performs one `commit_with_retry()` after the per-trigger loop. AppError still rolls back only that savepoint; a final commit failure rolls back the whole batch. Add regression coverage with a real/fake session asserting no inner commit |
| B6-F-06 | P2 | `backend/app/core/config.py:187` defines `EXECUTION_WORKER_ENABLED`; `backend/app/workers/execution_worker.py:366-409` does not enforce it | Gate worker execution processing on the flag while preserving heartbeat/kill-switch behavior; add regression test |
| B6-F-07 | P2 | `backend/app/services/automation_control_service.py:122-139`, `:167-183`: pause/resume state commit and audit append are separate | Rework to one commit so settings change and audit log are atomic; add regression test |
| B6-F-08 | P3 | `backend/app/services/builtin_execution.py:14-15`: example `set` step omits required `key` | Correct the example |
| B6-F-09 | INFO | no automation-specific limiter at `core/rate_limit.py:27-32`; no dead-letter state in `models/enums.py:208-217` | Out of Batch 6 contract; report as deferred, do not silently add |
| B6-F-10 | P2 | `backend/tests/api/test_automation_api.py:1-66` is auth-only; DB/RLS tests skip locally | Add targeted unit/service regressions for every fixed defect; report local DB skips exactly |

F.5 **No new backend contract**

- No new schema, migration, RLS, index, dependency, or generic endpoint.
- The only new frontend wrapper is for the already-existing execution-events endpoint.
- No provider health endpoint, no credential encryption endpoint, no workflow builder endpoint.
- New setting names are configuration fields/env-template documentation plus runtime validation only: `N8N_WEBHOOK_SECRET`, `WEBHOOK_TIMESTAMP_SKEW_SECONDS`, `WEBHOOK_REPLAY_TTL_SECONDS`. They do not change any API, schema, storage, or RLS contract.

---

## G. Frontend implementation plan

G.1 **Single typed permission mapping**

Add `frontend/src/lib/batch6-permissions.ts` with helpers derived from `can(role, permission)`:

- `workflowRead/Write/Manage`
- `automationRead/Write/Manage/Control`
- `executionRead/Write` where write maps to backend `workflow_write`
- `credentialManage`
- `deliveryRead/Write/Manage`

Use identical keys in nav, page gates, and action gates. `automation_manage` is `_ADMIN_ONLY` in both `backend/app/core/permissions.py:135` and `frontend/src/lib/permissions.ts:81`; preserve that mapping. Update only the credentials nav item to `credential_manage` because every credentials endpoint requires that key. Frontend gating is UX only; backend remains authority.

G.2 **Shared honest states**

Add reusable automation state components:

- read-denied state,
- loading state,
- empty state,
- `role="alert"` error with Retry,
- action-disabled reason helper.

Reuse existing UI primitives (`Card`, `Button`, `Modal`, `ConfirmDialog`, `Field`, `Spinner`, `EmptyState`, `PageHeader`, table primitives). Do not copy plain red error paragraphs or silent `null` permission fallback.

G.3 **Route work**

- `/workflows`: read gate, error+retry, create and edit modals, state/permission-conditional transitions.
- `/workflows/[id]`: read-only `TRIGGER → ACTION → ACTION` visualization using only actual `definition`; config/action detail; Run now; edit; transitions; no builder.
- `/triggers`: create/edit drawer, last-triggered column, backend query filters where available, denied/retry states, supported types only (`manual | event | schedule`).
- `/executions`: summary cards, duration, detail drawer, execution events timeline, error summary, local state guards plus backend permission key.
- `/credentials`: admin-only page/read gate, write-only warning, existing encrypted-value contract only, status/updated fields if present, denied/retry, no plaintext encryption claim.
- `/deliveries`: summary cards, ID/event/last-attempt fields, redacted metadata allowlist, no destination column unless backend field is proven.

G.4 **Tests**

Add page/SSR/markup tests for all six routes covering denied, loading, empty, error+retry, permission-hidden actions, state-dependent actions, and sensitive-data redaction. Extend service tests for the new execution-events wrapper. Keep existing Batch 5 tests unchanged except where a documented Batch 6 defect requires minimal correction.

---

## H. Database and schema-mirror plan

No database changes are in scope.

- No new migration, RLS policy, index, seed, edge function, or schema mirror change.
- The protected `0016` migration remains untouched.
- `database/schema/*.sql` is documentation of existing reality only; Batch 6 does not modify it.
- If a source audit reveals a schema drift defect that blocks a canonical Batch 6 route, record it as `BLOCKED BY ENVIRONMENT` or `REQUIRES FOUNDER DECISION`; do not silently change schema.

---

## I. Security and multi-tenant isolation

Threat model:

| Threat | Control |
|---|---|
| Cross-tenant workflow/trigger/execution/credential/delivery access | org derived from authenticated principal; repository filters; RLS reuse; tests |
| Privilege escalation via frontend | backend permissions authoritative; FE helpers mirror exact keys; no backend broadening |
| Webhook forgery | shared secret + HMAC signature over timestamp/nonce/raw body |
| Webhook replay | timestamp skew + nonce replay guard + existing idempotent lead handling |
| n8n SSRF/URL injection | base URL only from config; relative webhook path allowlist; no full URL from workflow config |
| Secret leakage | credentials write-only; no `encrypted_value`, provider keys, hostnames, or raw metadata in UI/log/API |
| Prompt injection into workflow actions | no AI-generated arbitrary actions; tool allow-lists; actor permission propagation |
| Infinite loops / budget burn | no new AI execution path; existing kill switch/budgets; no builder |
| Duplicate side effects | idempotency keys; resource-state guards; retry only allowed states |
| Unauthorized cancel/retry/pause/run | permission + state checks in UI and backend |
| Raw payload/provider metadata exposure | allowlist/redaction in delivery timeline and error summaries |

Security review must explicitly cover RBAC, tenant isolation, secrets, fail-closed behavior, request hardening, client-side safety, and residual risks.

---

## J. Integration and side-effect governance

| Integration | Current reality | Batch 6 treatment |
|---|---|---|
| n8n | configured by `N8N_BASE_URL`; client/tool/adapter exist | HARDEN; no live call in tests; mocks only |
| SMTP/email | account-security sender exists; no delivery-channel provider | REUSE narrow scope; no outbound email |
| WhatsApp | contact/channel data only; no provider | DEFERRED; truthful unavailable state |
| Calendar | agent registry marks FUTURE | DEFERRED; no calendar UI |
| Queue/scheduler/worker | implemented in Phase 5A–C | REUSE; tests use mocks where infra absent |
| AI tools/agents | registry, planner, budgets, kill switch implemented | REUSE; no new execution path |
| Credential consumption | vault complete; adapters mostly absent | REUSE vault; no new adapter without decision |
| Provider health | no endpoint | DEFERRED / founder decision |

Forbidden in this batch: fake provider connectivity, real outbound messages, paid AI calls, fake calendar success, arbitrary workflow code execution, globally enabled risky flags, and unapproved side effects.

---

## K. Documentation and final deliverables

Required files:

- `docs/PHASE6_BATCH6_IMPLEMENTATION_PLAN.md` — this frozen contract.
- `docs/PHASE6_BATCH6_IMPLEMENTATION_REPORT.md` — files changed, defects fixed, gate results, audit loop, limitations.
- `docs/PHASE6_BATCH6_SECURITY_REVIEW.md` — threat model, RBAC, tenancy, secrets, fail-closed, request/client safety, residuals.
- `docs/PHASE6_BATCH6_FINAL_ACCEPTANCE_REPORT.md` — scope, plan/process, backend, frontend, cross-layer/security, decisions, out-of-scope observations, final statement.
- Final founder report in the response, Sections A–Z, using only `PASS`, `FAIL`, `NOT VERIFIED`, `BLOCKED BY ENVIRONMENT`, `REQUIRES FOUNDER DECISION`.

Endpoint docs must be updated only if a documented API behavior changes. No docs may claim live integration, hydration/browser verification, or CI results that were not actually produced in this run.

---

## L. Decision register and founder constraints

| ID | Decision | Status | Batch 6 constraint |
|---|---|---|---|
| D-01 | Semantic color token source | REQUIRES FOUNDER DECISION | reuse existing tokens; no design re-freeze |
| D-02 | `/ai` single-Agent composition | REQUIRES FOUNDER DECISION | preserve Batch 5; no multi-agent work |
| D-03 | Contact/Demo submission backend | REQUIRES FOUNDER DECISION | out of scope; forms remain disabled/honest |
| D-04 | Task Board | REQUIRES FOUNDER DECISION | out of scope |
| D-05 | Onboarding Team step | REQUIRES FOUNDER DECISION | out of scope |
| D-06/D-17 | Appearance preferences | REQUIRES FOUNDER DECISION | route 36 excluded |
| D-07 | Monitoring Logs tab | REQUIRES FOUNDER DECISION | no Logs tab; Batch 4 behavior unchanged |
| D-08 | Pricing copy/limits | REQUIRES FOUNDER DECISION | out of scope |
| D-09 | Design asset availability | REQUIRES FOUNDER DECISION | PDF used; do not claim locked Sheet 1 fidelity |
| D-10 | Legal copy | REQUIRES FOUNDER DECISION | out of scope |
| D-11 | Account preferences | REQUIRES FOUNDER DECISION | route 36 excluded |
| D-12 | Monitoring metric visibility | PASS as implemented | reuse backend split; do not broaden |
| D-13 | AI Cancel permission | PASS as implemented | Batch 5 `agent_manage` gate unchanged |
| D-14/D-15/D-16 | Historical CRM decisions | PASS as implemented | out of scope |
| D-18 | Disabled vs hidden flagged routes | REQUIRES FOUNDER DECISION | Batch 5 disabled-state pattern reused; no hiding decision |
| B6-D-01 | Credential secret entry UX | REQUIRES FOUNDER DECISION | keep backend encrypted-value contract; no plaintext encryption claim |
| B6-D-02 | Approved founder `SEND_EMAIL`/`RUN_WORKFLOW`/`EXPORT` executor owner | REQUIRES FOUNDER DECISION | do not implement in Batch 6 |
| B6-D-03 | Provider/integration health endpoint | REQUIRES FOUNDER DECISION | no canonical route; defer |
| B6-D-04 | Local-time/per-trigger scheduling | REQUIRES FOUNDER DECISION | backend is UTC-only; expose truthful UTC helper text, no engine expansion |
| B6-D-05 | Dead-letter/quarantine state and automation rate limits | REQUIRES FOUNDER DECISION | not in canonical contract; report deferred, do not silently add |

No Batch 6 implementation decision may resolve a founder decision.

---

## M. Work packages and sequencing

1. **WP-1 Plan gate** — independent 17-check audit; correct until 17/17; freeze.
2. **WP-2 Backend hardening** — webhook authenticity/replay, n8n path/signing/metadata/retries, regression tests.
3. **WP-3 Shared frontend helpers/states** — typed permission mapping, error/denied states, tests.
4. **WP-4 Route corrections** — six canonical routes in dependency order: workflows → detail → triggers → executions → credentials → deliveries.
5. **WP-5 Services/types** — only existing-endpoint wrappers (execution events); no invented contracts.
6. **WP-6 Documentation** — update reports and docs from actual evidence.
7. **WP-7 Gates** — run current backend/frontend/contract checks; report exact skips.
8. **WP-8 Audit loop** — classify defects P0/P1/P2/P3/INFO; fix smallest robust fix + regression test; repeat until two consecutive full audits find zero unresolved in-scope P0/P1/P2/P3 defects.
9. **WP-9 Final reports + preservation proof** — four reports, founder A–Z, final git state check.

---

## N. Test and gate strategy

### N.1 Backend gates

Run from `backend/`:

- `\.venv\Scripts\python.exe -m pytest` (full suite; record skips exactly)
- `\.venv\Scripts\python.exe -m ruff check .`
- `\.venv\Scripts\python.exe -m mypy app`

Targeted automation/security tests must cover webhooks, n8n client, workflow API, executions, credentials, deliveries, tenancy, and new regressions. Concrete additions: route-order test for `/workflows/active`; generic status-patch rejection; nested trigger ownership; manual-start kill-switch; dispatcher no-commit savepoint behavior; worker flag; webhook signature/replay; n8n path/signing/retry; execution-events wrapper; all six page denial/error/action states; and delivery metadata redaction.

### N.2 Frontend gates

Run from `frontend/`:

- `npm run typecheck`
- `npm test`
- `npm run lint`
- `npm run build`
- `npm run format:check` (pre-existing drift must be reported exactly, not silently ignored)

### N.3 Contract gates

From repo root:

- `backend\.venv\Scripts\python.exe scripts\ci\contract_diff.py`
- `backend\.venv\Scripts\python.exe scripts\ci\docs_api_consistency.py`

Authoritative interpreter for every Python gate in this run is `backend\.venv\Scripts\python.exe`, invoked from the repository root for contract scripts (`backend\.venv\Scripts\python.exe scripts\ci\...`) and from `backend/` for pytest/ruff/mypy (`\.venv\Scripts\python.exe ...`). Pre-existing drift warnings are reported honestly; cannot be counted as Batch 6 failures unless introduced by this batch.

### N.4 Skip discipline

- DB/Redis/E2E skips are `BLOCKED BY ENVIRONMENT` for runtime proof where local infra is absent.
- Skipped tests are never counted as passing.
- Conditional skips (for flags such as intelligence triage) are reported with their exact reason.

---

## O. Audit loop and severity contract

Severity scale:

- **P0** — production/data/security break, cross-tenant leak, secret exposure, arbitrary execution.
- **P1** — wrong authorization, false availability, broken primary route contract.
- **P2** — missing contract test/documentation, misleading state, raw sensitive metadata.
- **P3** — minor drift/cosmetic issue that can mislead operators.
- **INFO** — observation requiring no Batch 6 change.

Loop rules:

1. Discover defect with evidence.
2. Classify severity.
3. Apply smallest robust fix plus regression test.
4. Re-run affected gate and full relevant suite.
5. Independent re-audit.
6. Repeat until two consecutive full audits report zero unresolved in-scope P0/P1/P2/P3 defects.

Audit streams: backend/security and frontend/route. Both must be clean twice.

---

## P. Risks and out-of-scope observations

Accepted/deferred risks:

- Local PostgreSQL/Redis unavailability blocks runtime proof of DB/RLS/worker behavior; CI provides those services.
- No live n8n/SMTP/WhatsApp/calendar provider verification in this batch.
- No browser hydration/click-through verification unless a browser session is explicitly available; SSR/markup tests are not a substitute.
- Batch 5 remains uncommitted by instruction; this is a preservation constraint, not a Batch 6 defect.
- Existing Makefile gate drift and pre-existing format/lint warnings are not Batch 6 failures unless changed here.
- Founder `SEND_EMAIL`/`RUN_WORKFLOW`/`EXPORT` execution ownership remains unresolved.

Out-of-scope observations must not be silently fixed.

---

## Q. Definition of done

A Batch 6 item is done only when:

1. Backend authority is unchanged or hardened; no permission broadening.
2. Frontend states are truthful and source-verified.
3. No secret, cross-tenant data, raw metadata, or fake success is exposed.
4. Tests cover the changed behavior.
5. Applicable gates are executed or honestly marked `NOT VERIFIED`/`BLOCKED BY ENVIRONMENT`.
6. Two consecutive full audits are clean for in-scope P0/P1/P2/P3 defects.
7. Documentation reflects actual evidence.
8. Preservation proof is recorded.

---

## R. Preservation proof requirements

Final verification must confirm:

- HEAD unchanged: `7f53ffaa…fac0`.
- Staging empty.
- `main` unchanged: `ba33074f…7cec`.
- Branch unchanged and no push performed.
- No commit, merge, deploy, PR change, or Batch 7 work.
- Protected `0016` migration untouched.
- All pre-existing Batch 5 and user artifacts preserved.
- No destructive Git command used.

---

## S. Acceptance checklist and independent 17-check plan gate

### S.1 Acceptance checklist

- [x] Independent plan quality gate passed 17/17 and appended here.
- [ ] Six canonical Batch 6 routes only; no invented routes.
- [ ] Backend permissions and tenant isolation authoritative and unchanged/broadened never.
- [ ] Frontend permission mapping aligned to backend keys.
- [ ] All six routes have truthful loading/empty/error+retry/read-denied/state-dependent action behavior.
- [ ] Read-only workflow visualization; no builder or arbitrary action execution.
- [ ] Credentials admin-only/write-only; no secret display or plaintext encryption claim.
- [ ] Webhook HMAC/replay and n8n path/signing/metadata hardening implemented with tests.
- [ ] Backend lifecycle/ownership/kill-switch/savepoint/worker-flag defects B6-F-01…B6-F-08 fixed with regression tests.
- [ ] Delivery metadata redacted; no fake destination.
- [ ] No live provider calls, paid AI calls, fake success, or globally enabled risky flags.
- [ ] Current Batch 6 gates executed; skips exact and not counted as passing.
- [ ] Two consecutive clean independent full audits with zero unresolved in-scope P0/P1/P2/P3 defects.
- [ ] Four required reports plus founder A–Z report written with allowed statuses.
- [ ] Protected `0016` and all user artifacts preserved; no staging/commit/push/merge/deploy/PR/main/Batch 7 changes.

### S.2 Independent 17-check plan quality gate

**Result: 17/17 PASS** — independent read-only audit completed 2026-11-21. Gates 1–17 were each verified against the plan text and spot-checked against live source (config, permissions, router surface, and the frozen scope inventory). All blocking and residual findings from earlier rounds were corrected before this result. The plan is frozen as `B6-PLAN-v1.0`; see §T.

The 17 checks are:

1. Baseline branch/HEAD/upstream and preservation inventory verified.
2. Protected migration constraint explicitly enforced.
3. Scope is exactly the six canonical Automation routes.
4. Batch 5 and out-of-scope work are preserved, not rebuilt or absorbed.
5. Every claimed capability is grounded in actual source evidence.
6. Capability classification is complete and uses the required vocabulary.
7. Backend authority, RBAC, and tenant isolation are explicit and unchanged/broadened never.
8. No unjustified new schema, migration, dependency, or backend contract.
9. Truthful unavailable, unauthorized, and state-dependent behavior is required.
10. No fake provider success, live side effect, arbitrary execution, or risky global flag.
11. Webhook, SSRF, replay, idempotency, secret, and AI-tool authorization threats are covered.
12. Test matrix covers unit/service/page/API/security/role/tenant layers.
13. Gate commands are current and Batch 6-specific.
14. Skips are reported exactly and never counted as passing.
15. Audit loop, severity taxonomy, and two-clean-audit rule are concrete.
16. Final reports and founder A–Z status vocabulary are specified.
17. Final preservation proof is concrete and verifiable.

---

## T. Plan freeze

**Status: FROZEN as `B6-PLAN-v1.0` (2026-11-21).**

§S.2 records 17/17 PASS from the independent read-only plan gate. Execution is now authorized strictly within this frozen scope. Any scope change requires an evidence-based amendment, a re-audit, and a new freeze identifier.
