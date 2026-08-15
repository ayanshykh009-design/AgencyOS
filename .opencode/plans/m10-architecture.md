# M10 — Phase 5D Final Verification & Production-Readiness Certification

**Status:** FROZEN (plan locked; implementation in progress)
**Owner:** Platform / Architecture
**Scope:** Verification + certification of M1–M9. No new product features, no
new tables, no schema changes beyond pinning existing migrations.

## Objective

Prove the AgencyOS backend (FastAPI + Supabase/Postgres, async workers) is
correct, tenant-isolated, layered, and production-deployable, then certify the
release GREEN and commit `chore(phase5d): complete M10 final verification`.

## Definition of done

1. Every existing backend test still passes; no regressions.
2. RLS / tenant isolation verified for representative + core tables (leads,
   conversations, ai_memories, knowledge_items) via disposable-DB integration
   tests that model the Supabase Auth runtime (`auth.uid()` → `tenant_org_id()`).
3. Migration integrity: all 27 SQL migrations pinned by SHA256; a content
   change fails CI.
4. Frontend/backend contract verified: FE `apiFetch` calls ⊆ backend OpenAPI
   routes (no drift). Endpoint docs are consistent (no phantom routes).
5. Layering enforced: endpoints → services → repositories; unified error
   envelope registered; production config fails closed.
6. Workers deployable: prod compose `worker` service launches all standalone
   workers via `backend/scripts/prod/start_workers.sh`; boot readiness tested.
7. One critical-journey E2E smoke (lead → note → pipeline) passes against a
   real DB.
8. Findings F-1..F-5 recorded; in-scope items fixed; out-of-scope items
   documented as recommendations.

## Verification artifacts (added this milestone)

| Artifact | Type | Runs in CI? | Runs locally? |
| -------- | ---- | ----------- | ------------ |
| `scripts/ci/contract_diff.py` | FE/BE route parity | ✅ | ✅ (no DB) |
| `scripts/ci/docs_api_consistency.py` | docs drift | ✅ | ✅ (no DB) |
| `backend/tests/unit/test_layering.py` | layering + envelope | ✅ | ✅ |
| `backend/tests/unit/test_config_production.py` | prod config fail-closed | ✅ | ✅ |
| `backend/tests/integration/test_rls_policy_coverage.py` | static RLS scan | ✅ | ✅ (no DB) |
| `backend/tests/integration/test_database_schema.py` (extended) | migration SHAs + leads/conversations RLS | ✅ | ⏭ skips (no DB) |
| `backend/tests/integration/test_workers_boot.py` | worker boot readiness | ✅ | ✅ (no DB) |
| `backend/tests/e2e/test_critical_journey.py` | critical journey | ✅ | ⏭ skips (no DB) |
| `frontend/src/lib/__tests__/permissions-consistency.test.ts` | FE/BE permission parity | ✅ | ✅ |
| `docker-compose.prod.yml` (`worker` service) + `backend/scripts/prod/start_workers.sh` | prod worker deploy | ✅ | n/a |
| CI jobs `contract-diff` + `worker-boot` (folded into `backend` pytest) | pipeline | ✅ | n/a |
| `docs/operations/backup-recovery.md`, `docs/deployment.md` (PITR), `docs/M10-FINDINGS.md` | ops/runbooks | n/a | n/a |

## Out-of-scope (documented, not fixed)

- **F-1 — Tool per-tool authorization gap.** Some tool handlers may not
  re-check the caller's org/permission at execution time. Verification only;
  fix tracked as a follow-up recommendation.
- **F-2 — Cumulative token budget.** Bounded per-call but no cross-session
  cumulative budget. Verification only; tracked as recommendation.

## In-scope findings fixed

- **F-3 — Production worker deployment.** Added prod `worker` service +
  launcher script.
- **F-4 — Frontend permission skew.** Added `workflow_read/write/manage` and
  `credential_manage` to the FE permission mirror; added a parity test that
  fails if the FE ever drifts from the backend `Permission` enum.
- **F-5 — Backup / DR runbook.** Added `docs/operations/backup-recovery.md`
  and linked it from `docs/deployment.md`.

## Certification gate

All runnable checks GREEN locally; DB/RLS/E2E/worker-boot gated through the CI
`postgres:16-alpine` service. If any CI gate is red, M10 is NOT certified and
the failing gate is fixed before commit.
