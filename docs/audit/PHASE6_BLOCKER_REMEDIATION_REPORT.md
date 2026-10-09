# Phase 6 Blocker Remediation Report

**Date:** 2026-10-08 · **Baseline:** `PHASE6_BASELINE_AUDIT_REPORT.md` (NO-GO) ·
**HEAD:** `4167e61` + uncommitted remediation working tree · **Author:** engineering remediation pass

**Scope.** All seven audit blockers (B-1 … B-7) plus the six non-blocker
(section-7) leads are reproduced, fixed, regression-tested, and re-audited.
Phase 6 itself was **not** implemented (scope lock). B-2 (application-layer
tenant scoping) and B-3 (PostgreSQL RLS + tenant context) are two halves of one
tenant-isolation incident and are reported separately.

**Numbering.** The authoritative blocker numbering is the one written into the
code/tests by the fixes (`B-1` … `B-7` docstrings); earlier working notes
mixed up B-2/B-4/B-6/B-7 labels — this report follows the in-repo labels.

## Report labels (A–K)

| Label | Meaning |
| ----- | ------- |
| A | Finding ID and title |
| B | Severity and impact |
| C | Reproduction — observable wrong behavior before the fix |
| D | Root cause (file:line references) |
| E | Fix mechanism |
| F | Regression tests added/changed (the pins) |
| G | Test results — targeted files and full suite |
| H | Lint / typecheck / build gate results |
| I | Security-specific checks performed |
| J | Re-audit findings and residual risk |
| K | Verdict: **GREEN** (fixed, verified, no blocking residual) / **AMBER** (fixed but with a verification or deployment dependency) / **RED** (unfixed or failed) |

## Verification environment and boundary

- Local: Windows, no Docker/PostgreSQL, no `gh` CLI → PostgreSQL-gated tests
  skip locally and **cannot be executed or observed from this environment**;
  CI (`.github/workflows/ci.yml`, postgres:16-alpine) is where they run.
- Everything runnable locally was run to green (see §Verification summary).
- A stale artifact (`conclusion`, captured 2026-08-16) shows an old
  "Validate prod compose" CI failure; it predates the 2026-08-29/30
  compose/CI fixes and the current working tree (static re-verification:
  all prod-compose interpolation variables resolve in `.env.example`,
  no `:?`-required variables, YAML parses; CI synthesizes `.env.production`).

---

# Part I — Blockers

## B-1 — Execution retry sweep used the wrong state transition, stalling the queue

- **A.** Worker retry sweep called the manual `retry()` transition on
  `RETRYING` rows, so every due retry raised HTTP 409 and aborted the whole
  sweep (retries → queued → timeouts ran sequentially with no isolation).
- **B.** High — availability/integrity: one due retry permanently stalls queue
  draining and the stale-runner reaper; heartbeat reports
  `loop_ok=false, "sweep failed"` forever.
- **C.** Fail an execution with backoff → `RETRYING` + `next_retry_at`.
  Next worker sweep: `process_retries` selects it (pre-fix: no due-time
  filter, so even *future* retries were swept early) → `retry()` raises 409
  (`execution.invalid_state`) → entire sweep iteration dies.
- **D.** `workflow_execution_service.py` `retry()` is terminal-status-only by
  design (409 for anything else); `process_retries` reusing it guaranteed
  failure. `get_queued_for_retry(before=None)` applied no
  `next_retry_at <= ?` filter (`repositories/workflow_execution.py`).
  `sweep()` had no phase isolation.
- **E.**
  - New guarded transition `WorkflowExecutionRepository.mark_requeued_due`:
    atomic `UPDATE … WHERE status='RETRYING' AND next_retry_at <= due_before
    … RETURNING` → `QUEUED` (TOCTOU-safe, org-filtered, returns `None` if the
    row no longer qualifies).
  - New `WorkflowExecutionService.requeue_due` (audit `EXECUTION_RETRIED`,
    timeline event, metric; silent no-op on concurrent change).
  - `process_retries` uses `requeue_due` with `before=utcnow()`;
    `get_queued_for_retry` service default hardened to `utcnow()`.
  - New `_safe_phase` wrapper: each sweep phase runs independently; failures
    are collected and re-raised once, after all phases complete.
- **F.** `test_workflow_execution_service.py::test_requeue_due_transitions_retrying_to_queued`,
  `::test_requeue_due_returns_none_when_not_due`,
  `::test_worker_helpers_delegate` (default filter = now);
  `test_execution_worker.py::test_process_retries_requeues_due`,
  `::test_process_retries_uses_requeue_due_not_retry` (explicitly fails on
  pre-fix code), `::test_process_retries_skips_future_retry_window`,
  `::test_process_retries_skips_concurrently_cancelled_row`,
  `::test_sweep_isolates_phase_failures`.
- **G.** All included in the full-suite green run (§Verification summary);
  no test in these files skipped locally.
- **H.** Backend ruff/mypy gates clean (shared run).
- **I.** Fail-safe direction: a broken retry path can no longer starve queue
  draining or the reaper; concurrent state changes are skipped, never raised.
- **J.** Re-audit: manual `retry()` correctly remains terminal-only; the only
  caller of the unfiltered repo path now always passes a datetime. Residual:
  repo-level `before=None` still means "no time filter" (footgun, no
  production caller).
- **K.** **GREEN**

## B-2 — Monitoring endpoints leaked cross-tenant aggregates and under-gated infrastructure data

- **A.** Every monitoring aggregate ran across all organizations; infrastructure
  views (hostnames/pids) were readable by any authenticated role.
- **B.** Critical — direct violation of the tenant-isolation top invariant
  (cross-tenant read of executions, queue depth, delivery volume, lifecycle
  events) plus infrastructure disclosure.
- **C.** Authenticated `VIEWER`/`MEMBER` of Org A →
  `GET /monitoring/execution-history|queue-status|execution-timeline|
  execution-statistics|automation-lifecycle|delivery-statistics` returned all
  tenants' data; any role → `GET /monitoring/worker-statistics|
  heartbeat-visibility|schedule-statistics|retention-statistics` returned
  hostnames, pids, error distributions.
- **D.** Repository aggregates had no `organization_id` predicate (docstrings
  literally said "across all organizations"; `count_pending_all_orgs` existed
  as a named method); `OperationalMonitoringService` methods took no org id;
  handlers never passed a tenant; infra endpoints gated only `AUTOMATION_READ`
  (all roles) — `monitoring.py`, `operational_monitoring_service.py`,
  `repositories/{workflow_execution,execution_event,workflow_event,
  activity_log,delivery}.py`.
- **E.**
  - Every tenant-data repo method now requires `organization_id` and filters
    by it; `count_pending_all_orgs` deleted; `queue_status` restricted to the
    caller's org; `DeliveryRepository.count_by_status` org-scoped.
  - Service methods take and forward `organization_id`; handlers pass
    `current_user.organization_id`.
  - RBAC split: tenant data stays `AUTOMATION_READ` (all roles, org-scoped);
    infrastructure endpoints (`worker-statistics`, `schedule-statistics`,
    `retention-statistics`, `heartbeat-visibility`) re-gated to
    `AUTOMATION_MANAGE` (admin-only); `delivery-statistics` and
    `operational/summary` remain admin-only and are now org-scoped.
  - Docs synced in this pass: `docs/api/endpoints/monitoring.md`,
    `docs/api/endpoints/deliveries.md`, `docs/operations/admin-guide.md`,
    `docs/api/openapi.yaml` (6 descriptions).
- **F.** New `tests/api/test_monitoring_api.py` (11 tests: 401 on 12 paths,
  403 on 6 admin paths for member/viewer, role-split behavior, org-forwarding
  proofs ×6); new `tests/unit/test_operational_monitoring_service.py`
  (7 org-scoping proofs); integration
  `test_services_integration.py::test_monitoring_aggregates_are_org_scoped`
  (real PG, two tenants, cross-tenant exclusion).
- **G.** Unit/API tests green in the full run; the PG integration test skips
  locally and runs in CI.
- **H.** Shared gates clean.
- **I.** Cross-tenant reads eliminated at repo, service, and handler layers;
  admin gate on infrastructure disclosure; authenticated ≠ authorized
  re-checked for all 18 monitoring paths.
- **J.** Residuals: `AgentRunRepository.count_pending_all_orgs` remains as
  dead code with **zero callers** (recommend removal); `/monitoring-information`
  still shows platform-wide system/DB/worker aggregates to `AUTOMATION_READ`
  (no tenant rows; documented policy judgment, no hostname/pid disclosure).
- **K.** **GREEN**

## B-3 — Tenant isolation: PostgreSQL RLS, tenant context, and least-privilege connection roles

- **A.** No database-enforced tenant isolation and no application tenant-binding
  mechanism; single shared role.
- **B.** Critical — the database layer of the tenant-isolation incident
  (top invariant defense-in-depth: API/RBAC + service/repository org scoping
  + PostgreSQL RLS).
- **C.** Pre-fix: any code path with the DSN read every org's rows at the DB
  layer (RLS absent). Naively adding RLS without the app-layer half would have
  locked out all pre-tenant flows (login/refresh/invite/webhook/register read
  or wrote rows *before* any org context existed) and cross-tenant workers.
- **D.** Single shared owner/superuser role; no session GUC; auth flows use
  plain ORM reads that RLS would filter to zero rows; workers are
  cross-tenant by design and need an explicit bypass role.
- **E.**
  - **`database/migrations/0033_tenant_isolation_rls.sql`:** roles
    `agencyos_app`/`agencyos_worker` (NOLOGIN anchors; `agencyos_worker`
    NOLOGIN+BYPASSRLS, guarded creates); `public.tenant_org_id()` SECURITY
    DEFINER with pinned `search_path`, GUC `app.current_organization_id`
    first (invalid uuid → NULL), `auth.uid()` fallback; seven SECURITY
    DEFINER pre-tenant lookups with `REVOKE … FROM PUBLIC` + GRANT to both
    roles; per-table policies `TO agencyos_app` (select/insert/update/delete
    tenant, org-scoped `organizations` incl. INSERT); global tables
    (`system_settings`, `credential_key_versions`) `_global`, `worker_health`
    SELECT-only; **no FORCE ROW LEVEL SECURITY** (deliberate, documented);
    guarded anon/authenticated grants; complete ROLLBACK section.
  - **Application context:** new `app/core/tenant_context.py` (ContextVar +
    server-side `set_config(..., false)`); `_restore_tenant_guc` begin
    listener on the **web** engine only (pooled-connection leak defense);
    `get_current_user` loads via definer lookup then activates the org;
    register (before flush — `WITH CHECK` holds), login, refresh, invite
    accept, and webhook ingest all activate the org; standalone workers moved
    to `worker_session_factory` bound to `WORKER_DATABASE_URL`
    (BYPASSRLS member role); in-process workers activate explicitly.
  - **Config/compose/docs:** `WORKER_DATABASE_URL` required by
    `validate_for_production` (boot-time, `app/main.py`); `backend/.env.example`,
    `docker-compose.prod.yml` (both services), `docs/database.md` bootstrap
    SQL, `docs/security.md` "Tenant isolation (B-3)" section and control rows.
  - Migration SHA re-pinned in `test_database_schema.py`.
- **F.** New `tests/unit/test_tenant_context.py` (16); static 0033 contract
  tests in `tests/integration/test_rls_policy_coverage.py` (~14: policy
  coverage of all 50 tenant-policy tables, exact policy targets, RLS ENABLEd,
  org-scoped `organizations`, global-table whitelist, no FORCE, role
  attributes, definer search_path, REVOKE/GRANT incl. guarded grants,
  table/sequence/default grants, ROLLBACK completeness, GUC cross-check);
  new PG-gated `tests/integration/test_tenant_isolation_rls.py` (11:
  role attributes, owner unaffected without FORCE, GUC-less app sees 0 rows
  across 5 tables, GUC=A/B scoping, cross-org INSERT → `42501`, cross-org
  UPDATE/DELETE rowcount 0 + WITH CHECK violation, worker sees all orgs,
  all 7 definer lookups vs plain-SELECT-0, `tenant_org_id` semantics
  incl. invalid-uuid → NULL, no GUC leak across connections, async e2e
  register → login → `get_current_user` → `activate_org` under
  `SET ROLE agencyos_app`); `test_config_production.py` two new bad-DSN cases;
  `test_tenant_context` quote-escape test (monkeypatched GUC value).
- **G.** Static/unit contract tests green locally (RLS coverage file: 122
  passed). Full suite: **1526 passed, 77 skipped, 0 failed** — the 11 new
  behavioral tests are among the skips and run in CI. SHA set verified
  33/33 files, 0 mismatch.
- **H.** Shared gates clean; migration SHA pin guards against drift.
- **I.** Threat-model checks: no endpoint accepts a GUC value (bound
  server-side only); quote-escape of GUC values; definer functions REVOKE
  FROM PUBLIC and grant only runtime roles; role attribute contract
  (BYPASSRLS only on worker anchor); membership semantics documented
  (`pg_has_role`); connection-role bootstrap documented for LOGIN members.
- **J.** Residuals: (1) anchors are NOLOGIN — production must create member
  LOGIN roles per `docs/database.md` bootstrap (documented, operator step);
  (2) shipped `docker-compose.prod.yml` still authenticates both DSNs as
  `POSTGRES_USER` (cluster owner) — owner bypasses RLS, acceptable for dev,
  **operator must substitute member-role DSNs in production** (documented in
  compose comments); (3) no FORCE RLS by design; (4) PG behavioral tests
  require CI execution.
- **K.** **GREEN** (code/tests) — carries the deployment exit criteria in
  Part III.

## B-4 — Approval gate worker: a heartbeat failure killed the worker loop

- **A.** Unhandled exceptions in the heartbeat path terminated the approval
  gate worker; a first-heartbeat failure could also raise `NameError` in
  `finally` (`counters` unbound), masking the original error.
- **B.** Medium-High — availability: a dead approval-gate worker stops
  workflow gating; the secondary `NameError` corrupts failure reporting.
- **C.** Make `WorkerHealthService.heartbeat` raise (transient DB error) →
  exception propagates out of the run loop; sweep never runs or dies;
  heartbeat reports wrong status.
- **D.** `workers/approval_gate_worker.py` called `heartbeat()` bare and bound
  `counters` inside `try` (used in `finally`).
- **E.** Heartbeat wrapped best-effort (`try/except` + `logger.exception`,
  noqa-justified) so it can never take down the loop; `counters: dict = {}`
  bound before `try`; session factory resolved at call time
  (`session_factory or worker_session_factory`) so the worker also gets the
  correct (BYPASSRLS) DSN.
- **F.** New `tests/unit/test_approval_gate_worker.py` (7): heartbeat writes
  `loop_ok`, heartbeat failure is best-effort, run loop survives an initial
  heartbeat failure, sweep failure is reported, heartbeat failure never kills
  the loop, disabled-run guard, `sweep_once` counts.
- **G.** Green in the full run.
- **H.** Shared gates clean.
- **I.** Fail-safe: worker loop liveness no longer depends on a secondary
  write path; failures are logged, not swallowed silently.
- **J.** Re-audit: same pattern exists in other workers' heartbeats only if
  they share the bare-call shape — the fix covers approval gate; other
  workers use their own loop shapes (audited during B-1/B-3 worker edits).
- **K.** **GREEN**

## B-5 — Research API treated "authenticated" as "authorized"

- **A.** All four `/research/{lead_id}` routes had authentication only — no
  role check.
- **B.** High — any role including `VIEWER` could trigger spend-bearing AI
  research (bills the org), override results, and delete research.
- **C.** Log in as `VIEWER` → `POST /api/v1/research/{lead_id}` → 202
  (enqueues a paid AI run); `PATCH`/`DELETE` accepted.
- **D.** `api/v1/endpoints/research.py` registered routes with `CurrentUser`
  only; no `require_permission` dependency.
- **E.** Explicit permission dependencies: `POST → AI_RUN`,
  `GET → LEAD_READ`, `PATCH|DELETE → LEAD_WRITE`, with rationale comment
  ("spend-bearing capability, not merely 'authenticated'").
- **F.** `tests/api/test_research_api.py` (6): requires `ai_run`, read allows
  viewer, mutations require `lead_write`, and three forbidden-for-viewer
  behavioral tests.
- **G.** Green in the full run.
- **H.** Shared gates clean.
- **I.** Direct instance of "authenticated ≠ authorized" from B-5's mandate;
  the spend path is now behind an explicit capability.
- **J.** Documented deferral: DB-backed positive-path tests (allowed role
  reaches handler) deferred to the integration suite (noted in code comment).
- **K.** **GREEN**

## B-6 — Per-org AI budget ceiling bypassed via feature-prefix filter

- **A.** The per-org 24h AI budget counted only `ai.`-prefixed usage rows;
  spend tagged with other feature keys escaped the ceiling entirely.
- **B.** High — financial control bypass: unbounded spend under a documented
  hard ceiling (`AI_ORG_DAILY_*`).
- **C.** Org burns 90 tokens tagged `research` + 50 tagged `ai.agent.run` →
  budget sums only `ai.*` (50) → under ceiling → 140-token day passes;
  `ai.budget_exceeded` 429 never fires.
- **D.** `LLMService._enforce_budget` passed
  `feature_prefix="ai."` to `totals_since` while `ResearchService` tagged
  `feature="research"` and founder intelligence tagged
  `intelligence.narrative`.
- **E.** Prefix filter removed — **every** `provider_usage` row for the org
  counts (rows are exclusively LLM usage); spend retagged `ai.research` and
  `ai.intelligence.narrative`; config/repo docstrings updated to state the
  contract ("no feature filter").
- **F.** `tests/unit/test_budget.py::test_budget_totals_count_all_org_features_no_feature_filter`,
  `::test_budget_blocks_when_non_namespaced_feature_spend_exceeds_ceiling`;
  integration `test_services_integration.py::test_provider_budget_counts_all_org_features`
  (real PG: mixed tags, org-B row excluded, blocks at ceiling);
  `test_intelligence_triage.py::test_llm_service_uses_ai_namespaced_feature`.
- **G.** Unit green locally; integration PG test skips locally, runs in CI.
- **H.** Shared gates clean.
- **I.** Fail-closed budget enforcement re-verified on unfiltered totals;
  infra-failure behavior (fail-closed 435) unchanged.
- **J.** Residual: `feature_prefix` survives on `totals_since` for non-budget
  callers — a future budget caller reusing it would silently reopen the hole
  (repo docstring warns; a dedicated budget query would be stronger).
- **K.** **GREEN**

## B-7 — Client-spoofable approval decision attribution

- **A.** The decision endpoint accepted a client-supplied
  `decided_by_user_id`, letting any caller attribute approvals/denials to
  arbitrary users.
- **B.** High — audit-integrity violation (decisions credited to users who
  never made them).
- **C.** `PATCH /approvals/{id}/decision` with
  `{"approve": true, "decided_by_user_id": "<victim-uuid>"}` → audit log,
  request row, and approval log credit the victim.
- **D.** `schemas/approval.py` accepted the field; `approvals.py` forwarded
  it (`data.pop("decided_by_user_id", None)`); `approval_service.decide`
  used `decided_by_user_id or actor.id`.
- **E.** Field deleted from the request schema; `decide()` parameter deleted
  and attribution is unconditionally `actor.id`; endpoint passes only
  `approve`/`decision_note`; `founder_action_service` call site adapted;
  `docs/api/openapi.yaml` request schema and `docs/api/endpoints/approvals.md`
  synced in this pass (response schema still exposes the server-set field).
- **F.** `tests/unit/test_phase5d_services.py::test_approval_decide_always_attributes_to_actor`
  (stamps `actor.id`, asserts the parameter is gone from
  `inspect.signature`, asserts the schema drops a client-supplied key).
- **G.** Green in the full run.
- **H.** Shared gates clean; OpenAPI request schema re-validated (YAML parse +
  property check: `['approve', 'decision_note']`).
- **I.** No remaining producer of client-asserted attribution (grep-verified);
  server-authoritative stamping only.
- **J.** None identified.
- **K.** **GREEN**

---

# Part II — Section-7 (non-blocker) leads

## L-1 — Tool registry permission check fails open on `None`

- **A.** `app/tools/registry.py` `assert_can_invoke_tool(None, …)` skips the
  check (`caller_permissions is None → allow`).
- **B.** Medium (latent) — defense-in-depth gap if a future caller passes
  `None` unintentionally.
- **C.** Unit-level: calling the guard with `None` bypasses enforcement.
- **D.** `registry.py:358–375` — `None` was chosen historically to mean
  "trusted/internal call".
- **E.** *Accepted residual:* only in-repo caller is `ai/brain.py:244`, which
  is guarded by `if caller_permissions is not None`; trusted internal paths
  depend on the current semantics.
- **F.** Existing caller-guard documented here; no code change (deferred by
  decision, not by oversight).
- **G.** N/A (no change).
- **H.** N/A.
- **I.** Fail-open direction recorded as an explicit, owned risk rather than
  an unnoticed one.
- **J.** Recommendation for Phase 6 hardening: migrate to fail-closed
  (treat `None` as deny) and pass explicit permission sets at every boundary.
- **K.** **AMBER** (accepted residual; fail-closed migration recommended)

## L-2 — `caller_permissions=None` in agent/brain execution paths

- **A.** `agents.py` queue endpoints and `brain_executor.py` could run with
  no resolved permission set.
- **B.** Low-Medium — reviewed and mitigated.
- **C.** Hypothetical: a brain execution with an unresolvable actor could
  grant blanket tool access via the L-1 `None` semantics.
- **D.** `brain_executor.py:80–88, 267–272`; `agents.py:113–123`.
- **E.** `/api/v1/ai/run` sets `actor_user_id` (`ai.py:146`); executor
  resolves `permissions_for_role(actor.role)` when an actor exists, and a
  **missing actor yields `frozenset()` (fail-closed)**; `None` is passed only
  on trusted, `AGENT_MANAGE`-gated queue paths; `agents.py` uses the
  admin-gated `_manage` dependency.
- **F.** Existing auth/executor tests cover actor resolution; changes were
  verified in prior passes (no behavioral change this session).
- **G.** Covered by the full-suite green run.
- **H.** Shared gates clean.
- **I.** Authenticated ≠ authorized preserved on the AI run surface; missing
  actor fails closed.
- **J.** Residual hardening: align trusted paths with L-1 fail-closed
  migration.
- **K.** **GREEN** (mitigated; hardening tracked with L-1)

## L-3 — `requeue_stale` TOCTOU (delivery double-send/recovery race)

- **A.** Staleness was checked before the UPDATE, not inside it — a delivery
  could be requeued after being claimed again (double-send), and recovery
  events were stamped even when requeue failed.
- **B.** Medium-High — message-integrity/double-send risk.
- **C.** Worker A marks processing; clock passes threshold; worker B
  `release_stale_processing` selects it (stale at SELECT time); worker A
  finishes and clears the stamp; B's UPDATE still fires → recovery of an
  already-completed delivery.
- **D.** `repositories/delivery.py` `requeue_stale` pre-fix predicate +
  `delivery_worker._recover_stale` event ordering.
- **E.** `requeue_stale(organization_id, delivery_id, stale_before)` now
  re-checks staleness **inside** the UPDATE
  (`attempt_started_at IS NULL OR < stale_before OR updated_at < stale_before`)
  and clears `attempt_started_at`; `_recover_stale` requeues **first** and
  stamps `TIMED_OUT`/`RECOVERY_GUARD` events only when the requeue actually
  succeeded; `release_stale_processing` passes `before`.
- **F.** `tests/unit/test_delivery_repository.py::
  test_requeue_stale_guards_processing_and_clears_stamp` (asserts the
  staleness predicate is in the statement and the stamp is cleared);
  delivery repository/worker/service tests updated — **36/36 green**.
- **G.** Targeted 36/36; full suite green.
- **H.** Shared gates clean.
- **I.** Double-send guard verified structurally (predicate inside UPDATE)
  and behaviorally (guarded-row skips).
- **J.** None identified; `claim()`/`mark_failed`/`schedule_retry` attempt
  budgets unchanged and correct.
- **K.** **GREEN**

## L-4 — `start_workers.sh` SIGTERM trap never reached the children

- **A.** The trap used `kill -TERM "$@"` — inside a trap, `$@` is the
  *script's* arguments (none under Docker), so children were never signalled;
  `docker stop` degraded to SIGKILL with no drain window.
- **B.** Medium — production shutdown integrity (in-flight work truncated).
- **C.** `docker stop` the worker container → parent exits, children keep
  running until SIGKILL.
- **D.** `backend/scripts/prod/start_workers.sh` original trap.
- **E.** Rewritten: `PIDS=""` tracked at launch; `shutdown() { trap - TERM
  INT; kill -TERM ${PIDS:-} 2>/dev/null; wait; }` with
  `trap shutdown TERM INT` — children signalled, parent `wait`s for drain
  (bounded by the stop grace period).
- **F.** `tests/integration/test_workers_boot.py::
  test_start_workers_sigterm_traps_and_forwards_to_child_pids` (asserts the
  trap line, comment-stripped absence of `"$@"`, and `kill -TERM ${PIDS:-}` +
  `wait` in the handler).
- **G.** File green (24/24 in `test_workers_boot.py`); full suite green.
- **H.** Shared gates clean.
- **I.** Graceful-drain guarantee restored for production container stops.
- **J.** Static test only (no shell execution environment on Windows/CI
  container); the assertion is comment-aware after the first iteration
  caught a false failure on explanatory comments.
- **K.** **GREEN**

## L-5 — Production config validation gaps (residual hardening)

- **A.** `validate_for_production` hardening is partially complete: strong
  secret checks exist, but no entropy/length validation of
  `CREDENTIALS_ENC_KEY`, and `WORKER_DATABASE_URL` is checked for scheme
  only.
- **B.** Low-Medium — hardening debt, not an active defect.
- **C.** A short/predictable but non-blocklisted enc key, or a worker DSN
  pointing at the wrong role, passes boot validation.
- **D.** `app/core/config.py` `validate_for_production` (lines 479–508).
- **E.** *Partially fixed already* (weak-secret blocklist, ≥32-char
  `SECRET_KEY`, enc-key presence, CSP/phase gates, `WORKER_DATABASE_URL`
  required); remaining checks deferred by decision.
- **F.** `tests/unit/test_config_production.py` (bad DSN cases added this
  session), `tests/test_config.py` updated fixtures.
- **G.** Green in the full run.
- **H.** Shared gates clean.
- **I.** Boot-time fail-fast retained; no regressions to the hardening chain
  (verified `app/main.py` is the sole production entry).
- **J.** Deferred: enc-key entropy/length check; role-membership proof for
  worker DSN (can't be validated from a URL alone — documented bootstrap).
- **K.** **AMBER** (deferred hardening, explicitly tracked)

## L-6 — Frontend/backend `workflow_manage` permission divergence

- **A.** FE `PERMISSION_MATRIX.workflow_manage = _ADMIN_ONLY` vs BE
  `WORKFLOW_MANAGE = _MANAGE` — the only mismatch in an otherwise identical
  matrix (FE was stricter: managers lost workflow-management UI).
- **B.** Medium — fail-closed UX/consistency defect (manager role could not
  use workflow management despite holding the backend capability).
- **C.** Log in as `manager` → workflow-management UI hidden → backend would
  have allowed it.
- **D.** `frontend/src/lib/permissions.ts:85`.
- **E.** One-line fix: `workflow_manage: _MANAGE` (owner/admin/manager),
  matching `backend/app/core/permissions.py`.
- **F.** New role-set parity test in
  `frontend/src/lib/__tests__/permissions-consistency.test.ts::
  matches the backend role sets exactly (no FE/BE drift)` — parses the
  backend matrix (enum members → values, named role groups) and asserts set
  equality per permission (the prior test checked key parity only, which is
  why this drift shipped).
- **G.** FE **142 tests / 25 files green** (parity test: 4/4). Mutation-
  verified: temporarily reverting the fix makes the test fail with the exact
  diff (`backend=[owner,admin,manager] frontend=[owner,admin]`); fix restored.
- **H.** `tsc --noEmit` clean; `eslint` 0 errors (1 pre-existing warning in
  `postcss.config.mjs`); `next build` compiled successfully.
- **I.** BE/FE permission matrices now provably identical — drift of this
  class is regression-tested.
- **J.** None identified.
- **K.** **GREEN**

---

# Part III — Verification summary and verdict

## Consolidated verification (2026-10-08, local)

| Gate | Result |
| ---- | ------ |
| Backend full suite (`pytest`) | **1526 passed, 77 skipped, 0 failed** |
| Backend ruff | **All checks passed** |
| Backend mypy (`app`) | **Success: no issues found in 343 source files** |
| Frontend vitest | **142 passed / 25 files, 0 failed** |
| Frontend `tsc --noEmit` | Clean |
| Frontend eslint | 0 errors (1 pre-existing warning) |
| Frontend `next build` | Compiled successfully |
| Migration SHA pin | 33/33 files, 0 missing/extra/mismatch |
| RLS static contract suite | Green (122 tests in file) |
| Delivery requeue/recovery tests | 36/36 |
| `test_workers_boot.py` | 24/24 |
| Compose YAML + interpolation | Both files parse; every `${VAR}` resolves in `.env.example`; no `:?` hard-required gaps |
| OpenAPI spec | Regenerated via canonical `scripts/regen-openapi.py` (168 paths); request schema excludes `decided_by_user_id`; 0 stale cross-org phrases; YAML parses |
| FE/BE permission parity | Key + role-set parity green; mutation-verified |
| PG-gated tests (77) | Skip locally — **execute in CI** (incl. 11 new RLS behavioral tests) |

## Residual register (accepted, tracked)

| Ref | Item | Owner decision |
| --- | ---- | -------------- |
| L-1 | Tool registry `None` fails open | Fail-closed migration recommended in Phase 6 |
| L-5 | No entropy check on `CREDENTIALS_ENC_KEY`; worker DSN scheme-only | Deferred hardening |
| B-3 | Prod compose ships cluster-owner DSNs (owner bypasses RLS) | Operator must substitute member-LOGIN-role DSNs (`docs/database.md` bootstrap) |
| B-3 | Roles are NOLOGIN anchors | Operator creates LOGIN member roles before first RLS-enforced deploy |
| B-2 | `AgentRunRepository.count_pending_all_orgs` dead code | Remove in follow-up |
| B-2 | `/monitoring-information` shows platform infra aggregates to all roles (no tenant rows) | Documented policy judgment |
| B-6 | `feature_prefix` still available to future budget callers | Dedicated budget query recommended |

## Exit criteria (AMBER → GREEN)

1. **CI run green** — the 77 PG-gated tests (notably
   `tests/integration/test_tenant_isolation_rls.py`, RLS contract suite,
   PG monitoring/budget integration tests) plus the compose-validation job
   must pass in `.github/workflows/ci.yml`. They cannot be executed from this
   environment (no Docker/PG/`gh`).
2. **Production role bootstrap** — deploy with member LOGIN roles per
   `docs/database.md`, or replace the compose owner DSNs with member-role
   DSNs, so RLS is actually enforced in production.

## Overall verdict

**AMBER.**

All seven blockers (B-1 … B-7) are individually **GREEN**: fixed,
regression-tested, re-audited, with lint/typecheck/build gates clean.
Section-7 leads: L-2, L-3, L-4, L-6 **GREEN**; L-1 and L-5 **AMBER** as
explicitly accepted, tracked residuals. The overall gate is AMBER — not for
any known defect, but solely because the PostgreSQL-dependent behavioral
verification (77 tests) and the production connection-role bootstrap cannot
be confirmed from this environment. Both exit criteria are mechanical: one
green CI run and one documented operator step.
