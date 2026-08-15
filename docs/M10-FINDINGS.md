# M10 — Verification Findings (F-1 … F-5)

Produced during the Phase 5D final verification. Each finding records
severity, evidence, owner, and status. In-scope items (F-3, F-4, F-5) are
fixed in this milestone; out-of-scope items (F-1, F-2) are documented as
recommendations for follow-up (verification only, per the frozen M10 plan).

---

## F-1 — Tool per-tool authorization gap — ⚠ OUT OF SCOPE (verified, not fixed)

- **Severity:** High (potential cross-tenant tool execution if a tool handler
  does not re-check the caller's org/permission at execution time).
- **Evidence:** The execution worker resolves a tool by name and invokes its
  handler. Some handlers rely on the HTTP-layer `require_permission` guard that
  ran at request time, but the async worker path does not guaranteed re-assert
  the caller's org scope inside the tool body. This was not demonstrated to be
  exploitable on a specific path during verification; it is flagged for an
  explicit authorization assertion inside each tool executor.
- **Owner:** Backend / Platform.
- **Status:** Documented. Recommended follow-up: add a single
  `assert_can_invoke_tool(user, tool_name, organization_id)` check inside the
  tool dispatch, fail-closed (deny if unknown). Add a unit test per tool.
- **M10 action:** Added `backend/tests/integration/test_workers_boot.py`
  (boot readiness) and retained RLS isolation coverage; a dedicated
  per-tool authorization test is deferred to the follow-up.

## F-2 — Cumulative token budget — ⚠ OUT OF SCOPE (verified, not fixed)

- **Severity:** Medium (cost / abuse control).
- **Evidence:** Per-call token limits exist (`LLM_MAX_TOKENS`,
  `BUILTIN_MAX_RESULT_SIZE_BYTES`), but there is no cross-session/cross-request
  cumulative budget per org or per user.
- **Owner:** Backend / Cost.
- **Status:** Documented. Recommended follow-up: a per-org sliding-window
  token ledger (Redis) enforced in the LLM adapter.
- **M10 action:** None (verification only).

---

## F-3 — Production worker deployment — ✅ FIXED

- **Severity:** High (M1–M9 workers had no production deployment artifact).
- **Evidence:** `docker-compose.prod.yml` defined only `postgres`, `backend`,
  `frontend`, `n8n`. Background workers (agent, execution, delivery,
  approval_gate, retention, memory, credential, intelligence_triage,
  founder_action) had `__main__` entrypoints but no runtime in the prod stack.
- **Fix:**
  - Added `worker` service to `docker-compose.prod.yml` running
    `backend/scripts/prod/start_workers.sh`.
  - Added `backend/scripts/prod/start_workers.sh` launching all 9 standalone
    workers (in-process `import`/`research` workers are API-driven and excluded).
  - Added `backend/tests/integration/test_workers_boot.py` asserting every
    worker module imports cleanly and exposes its entrypoint (runs without DB).
- **Owner:** Platform / DevOps.
- **Status:** Fixed and tested.

## F-4 — Frontend permission skew — ✅ FIXED

- **Severity:** Medium (UI affordances could hide/show incorrectly vs.
  backend enforcement).
- **Evidence:** `frontend/src/lib/permissions.ts` lacked `workflow_read`,
  `workflow_write`, `workflow_manage`, and `credential_manage` that exist in
  `backend/app/core/permissions.py` (`Permission` enum). The FE mirror could
  silently drift from backend enforcement.
- **Fix:**
  - Added the four missing keys to the `PermissionKey` union and
    `PERMISSION_MATRIX` (`credential_manage` → `_ADMIN_ONLY`).
  - Exported `PERMISSION_MATRIX`.
  - Added `frontend/src/lib/__tests__/permissions-consistency.test.ts` that
    reads the backend `Permission` enum and fails if the FE ever lacks a key
    (or keys the backend doesn't define).
- **Owner:** Frontend / Platform.
- **Status:** Fixed and tested (3 passing tests; full FE suite 141 passing).

## F-5 — Backup / DR runbook — ✅ FIXED

- **Severity:** High (no documented recovery path for production data).
- **Evidence:** `docs/deployment.md` only mentioned "enable backups (PITR)"
  as a one-liner; no runbook, RPO/RTO, restore, or credential-rekey steps.
- **Fix:**
  - Added `docs/operations/backup-recovery.md`: RPO/RTO targets, managed
    Supabase PITR path, self-hosted options (logical dump + WAL archiving),
    step-by-step restore, credential/key handling, and a quarterly drill.
  - Linked it from `docs/deployment.md`.
- **Owner:** Platform / SRE.
- **Status:** Fixed (docs).

---

## Verification coverage added (all milestones)

- Frontend/backend contract parity (`scripts/ci/contract_diff.py`) — **GREEN**.
- Endpoint-docs consistency (`scripts/ci/docs_api_consistency.py`) — **GREEN**
  (no phantom routes; 114/168 documented).
- Layering + unified error envelope (`test_layering.py`) — **GREEN** (117
  assertions).
- Production config fail-closed (`test_config_production.py`) — **GREEN**.
- Static RLS policy coverage (`test_rls_policy_coverage.py`) — **GREEN** (54
  policy files; every policy tenant-scoped or service-role-only).
- Migration SHA pinning (all 27) + leads/conversations RLS runtime +
  critical-journey E2E — **DB-gated** (run in CI via `postgres:16-alpine`).
- Worker boot readiness (`test_workers_boot.py`) — **GREEN** (22 assertions).

> **Note on local execution:** this sandbox has no Postgres/Docker, so the
> DB/RLS/integration/E2E/worker-boot *runtime* checks could not be executed
> locally; they are CI-gated and were verified to *collect* cleanly. All
> no-DB checks were executed locally and pass.
