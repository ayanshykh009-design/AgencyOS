# AgencyOS — Skipped Test Decisions

**Generated:** 2026-10-30 (final Phase 6 readiness audit)

## Summary

- Total collected tests: **1870** (backend).
- CI (exact SHA `e020aae3996b52cf4e265ea1315e80afc34e24ad`, run `41014724532`): **1870 passed, 0 skipped**.
- Local (no PostgreSQL/Redis): **1769 passed, 101 skipped**.
- Frontend: Vitest suite (count not separately tallied here; see `npm test` in CI, which passed).

Every skip in the repository is environment-gated (`pytest.importorskip` + `skipif` on service availability). No test is marked skip for a behavioral reason. No skip markers were added, removed, or weakened during this audit.

## Classification key

- **A — Verified in CI:** skipped locally, executed and passed in CI.
- **B — Essential for current internal use:** must have genuine executed evidence.
- **C — Deferrable:** optional capability outside current internal-use scope.
- **D — Unclear:** needs investigation.

## Inventory

| Test module | Skip condition | Tests (approx.) | Category | CI evidence |
|---|---|---|---|---|
| `tests/integration/test_services_integration.py` | `psycopg2` import + PG reachability | ~40 | A/B | run 41014724532: passed |
| `tests/integration/test_tenant_isolation_rls.py` | `psycopg2` import + PG reachability | ~25 | A/B | run 41014724532: passed |
| `tests/integration/test_m11_ai_run.py` | `psycopg2` import + PG reachability | ~10 | A/B | run 41014724532: passed |
| `tests/integration/test_founder_integration.py` | `psycopg2` import + PG reachability | ~15 | A/B | run 41014724532: passed |
| `tests/integration/test_database_schema.py` | `psycopg2` import + PG reachability | ~12 | A/B | run 41014724532: passed |
| `tests/integration/test_auth_concurrency.py` | `psycopg2` import + PG reachability | ~8 | A/B | run 41014724532: passed |
| `tests/integration/test_outreach_authorization.py` | `psycopg2` import + PG reachability | 12 | A/B | run 41014724532: passed |
| `tests/integration/test_resend_cooldown_redis.py` | `redis` import + Redis reachability | ~6 | A/B | run 41014724532: passed |
| `tests/e2e/test_critical_journey.py` | PG reachability (conftest) | ~5 | A/B | run 41014724532: passed |

## Decisions

- **Category A** applies to all of the above: the exact tests execute and pass in CI against the real `postgres`/`redis` services. No redundant local setup is required; local developers may run them with `TEST_POSTGRES_URL`/`TEST_REDIS_URL` if desired.
- **Category B** (essential) is satisfied by CI evidence for auth/session, tenant isolation/RLS, authorization/RBAC, core CRM, outreach writes, and resend cooldown atomicity.
- **No Category C or D entries remain** for the backend skip inventory: every skip is a service-availability gate with CI proof.
- Frontend: no `it.skip`/`describe.skip` markers found in the inspected `src/`; Vitest runs the full configured suite in CI (`npm test`) which passed.

## Outstanding risks

- Local developers without PostgreSQL cannot reproduce PG-backed failures; CI is the authority. This is an accepted, documented trade-off, not a coverage gap.
- The E2E critical-journey suite depends on the backend stack being up; it passes in CI.

## Conclusion

No skipped test lacks CI evidence. No essential test is unverified. No test was deleted or weakened. Skip inventory is fully accounted for and classified.
