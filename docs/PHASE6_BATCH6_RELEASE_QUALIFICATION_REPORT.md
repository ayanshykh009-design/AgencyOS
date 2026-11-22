# AgencyOS Phase 6 — Batch 6 Release Qualification Report

**Date:** 2026-11-21  
**Plan contract:** `docs/PHASE6_BATCH6_IMPLEMENTATION_PLAN.md`, frozen as `B6-PLAN-v1.0`  
**Branch:** `feat/phase6-commercial-v1`  
**Baseline HEAD:** `7f53ffaa5456b7ef7d1f58d8a441c086bf05fac0`  
**`main`:** `ba33074fe8bbcc43382bc0a7d77d24ce682c7cec`  
**Overall qualification:** `REQUIRES FOUNDER DECISION`

Batch 6 is qualified for **local, in-scope completion** only. It is **not fully release-certified**: real PostgreSQL/Redis/RLS runtime proof is `BLOCKED BY ENVIRONMENT`, several QA dimensions are `NOT VERIFIED` or `BLOCKED BY ENVIRONMENT`, and the open founder decisions remain `REQUIRES FOUNDER DECISION`. Green unit suites alone are not treated as release certification.

**Status vocabulary used throughout:** `PASS`, `FAIL`, `NOT VERIFIED`, `BLOCKED BY ENVIRONMENT`, `REQUIRES FOUNDER DECISION`.

---

## 1. Required 26-item qualification matrix (A–Z)

| # | Area | Status | Evidence and limits |
|---|---|---|---|
| A | Frozen plan and process boundary | `PASS` | `B6-PLAN-v1.0` unchanged; independent plan gate 17/17; WP-1…WP-9 executed without scope change. |
| B | Branch, HEAD, `main`, staging and protected artifact preservation | `PASS` | Branch/HEAD/`main` match baseline; staged-change list empty; protected migration was never opened, read, inspected, diffed, hashed, staged, modified, renamed or deleted. |
| C | Prohibited actions | `PASS` | No commit, push, merge, deploy, reset, clean, stash, destructive command, PR change, `main` change or Batch 7 work occurred. |
| D | Implementation report reconciliation | `PASS` | `PHASE6_BATCH6_IMPLEMENTATION_REPORT.md` lists the `use-auth` fix, contrast fix, Round 5 fixes, new tests, the integrated 51-file/360-test count and final gate reruns. |
| E | Security review reconciliation | `PASS` | `PHASE6_BATCH6_SECURITY_REVIEW.md` now records browser-only verification, exact RBAC semantics, fast-refresh/hydration fix, shared-component contrast fix, `commit=False` rollback scope and residual blockers. |
| F | Final acceptance report reconciliation | `PASS` | `PHASE6_BATCH6_FINAL_ACCEPTANCE_REPORT.md` no longer contradicts itself on browser verification; counts, audit rounds and environment limits are corrected. |
| G | Backend route and contract scope | `PASS` | No new backend route, schema, migration, RLS policy, generic endpoint or backend contract. Contract script exit 0: 177 backend routes, 108 unique frontend calls. |
| H | Backend RBAC and tenant isolation | `PASS` | Org derivation remains authoritative; nested trigger ownership tightened; no permission matrix broadening; source and regressions inspected. |
| I | Webhook authenticity and replay hardening | `PASS` | Raw-body HMAC-SHA256 with timestamp/nonce, org-scoped replay guard, fail-closed deployed Redis behavior and bounded local fallback are implemented. Redis runtime proof is separately `BLOCKED BY ENVIRONMENT`. |
| J | n8n transport hardening and redaction | `PASS` | Relative `/webhook/...` allowlist, config-only base URL, signed org/actor/workflow/execution/idempotency metadata, bounded transient retries, response-body-free logs/errors. |
| K | Execution lifecycle and worker correctness | `PASS` | Route order, generic status bypass, manual-start kill switch, dispatcher savepoint commit, worker flag, atomic pause/resume audit and built-in example defects fixed with regressions. |
| L | Credential handling | `PASS` | Admin-only backend contract, write-only UI, no secret rendering; rotate/delete click-through verified in local synthetic browser QA. |
| M | Delivery outbox and state-aware actions | `PASS` | Allowlist redaction, detail timeline, state-aware retry/cancel with exact `{}` bodies; manual dispatch remains unavailable with an honest reason. |
| N | Six canonical routes | `PASS` | `/workflows`, `/workflows/[id]`, `/triggers`, `/executions`, `/credentials`, `/deliveries` all rendered and exercised in the in-app browser with zero console errors after the final fixes. |
| O | Frontend permission helper and role semantics | `PASS` | Exact backend keys mirrored; shared matrix untouched; `member` is write-capable, `viewer` read-only, credentials admin-only. Synthetic API was corrected to mirror real backend policy. |
| P | Browser role QA | `PASS` | Owner/admin click-through request bodies, member write controls, viewer denials and backend `403`s, and unauthenticated redirects verified with a temporary synthetic API outside the repository. This is not real backend/DB/Redis proof. |
| Q | Loading, empty, error, retry and detail states | `PASS` | Empty and forced-failure states verified on all six routes; Retry recovery, execution detail timeline and delivery detail/attempt history verified. |
| R | Accessibility and contrast | `PASS` | Lighthouse accessibility `1.0` with zero failures on all six routes and the workflow create modal after replacing 2.53:1 `text-gray-400` with `text-gray-600` on route and shared `Field`/`Modal`/`site-nav` components; regression test expanded. Reduced-motion CSS, semantic tables, alerts, dialogs and aria labels verified. |
| S | Explicit responsive viewports | `BLOCKED BY ENVIRONMENT` | 360×800, 768×1024, 1024×768 and 1440×900 could not be emulated by the in-app browser; no horizontal overflow was observed at the available viewport. |
| T | Full keyboard navigation | `NOT VERIFIED` | Focus ring was verified programmatically (`rgb(229, 151, 0) auto 1px`), but browser `Tab` presses did not move `document.activeElement` from `BODY` in this harness. |
| U | Backend local gates | `PASS` | Final integrated full rerun: **1942 passed, 101 skipped, 0 failed**, 72 warnings in 109.13s. `ruff check .` clean; `mypy app` clean in 355 source files. Skips are listed below and are never `PASS`. |
| V | Frontend local gates | `PASS` | `npm test`: 51 files / **360 passed, 0 failed, 0 skipped**; typecheck clean; lint 0 errors and 1 pre-existing warning; build compiled 38 pages; targeted Prettier clean. |
| W | Contract and documentation consistency scripts | `PASS` | `contract_diff.py` and `docs_api_consistency.py` both exit 0; 177 routes, 108 frontend calls, 30 doc files, 159 documented paths. Uncalled-route and undocumented-route warnings are pre-existing detector/documentation drift. |
| X | Repository formatting and dependency scanners | `FAIL` | Repository-wide `npm run format:check` fails on 18 pre-existing out-of-scope files; all Batch 6 files pass targeted Prettier. Local `npm audit --audit-level=critical` exits 0; full audit retains 7 moderate `minimatch`-chain findings and 1 high `zod` finding documented as accepted exceptions. Local OSV/`pip-audit` executables are `BLOCKED BY ENVIRONMENT`. |
| Y | Runtime infrastructure and fresh remote CI | `BLOCKED BY ENVIRONMENT` | Disposable Redis `8.10.3` on `127.0.0.1:6380` passed 24 targeted tests; disposable PG16 `16.16` proved binary/connectivity viability, but migration-backed fixtures remain intentionally unrun because they read all migration SQL including a protected artifact. Docker/Compose and WSL remain unavailable. Fresh exact-SHA CI evidence is `NOT VERIFIED`; no historical CI result was reused. |
| Z | Founder decisions and final release status | `REQUIRES FOUNDER DECISION` | D-02, D-18, B6-D-01, B6-D-02, B6-D-03, B6-D-04 and B6-D-05 remain open. No answer was assumed and no deferred feature was silently implemented. |

---

## 2. Release qualification conclusion

Local evidence supports `PASS` for the frozen Batch 6 implementation scope, local static/browser QA and locally runnable gates, with the independent defect-fix loop satisfied by two consecutive clean audits (Rounds 6 and 7). It does **not** support full release certification. The blocking qualification gaps are:

- `BLOCKED BY ENVIRONMENT`: full migration-backed PostgreSQL/RLS runtime proof, exact viewport emulation, local OSV/`pip-audit` scanners and fresh remote CI infrastructure.
- `NOT VERIFIED`: full keyboard tab traversal and fresh exact-SHA CI result from a remote runner. Targeted disposable Redis and local npm audit gates passed and are not counted as full-stack proof.
- `FAIL`: repository-wide Prettier check (pre-existing, out-of-scope drift only).
- `REQUIRES FOUNDER DECISION`: all decisions listed in item Z.

No commit, push, merge, deploy, PR change, `main` change or Batch 7 work was performed.

---

## 3. Final gate commands and results

| Gate | Status | Result |
|---|---|---|
| Backend full pytest | `PASS` | 1942 passed, 101 skipped, 0 failed, 72 warnings in 109.13s |
| Backend ruff | `PASS` | `All checks passed!` |
| Backend mypy | `PASS` | `Success: no issues found in 355 source files` |
| Frontend tests | `PASS` | 51 files passed; 360 tests passed, 0 failed, 0 skipped |
| Frontend typecheck | `PASS` | Exit 0 |
| Frontend lint | `PASS` | Exit 0; 0 errors, 1 pre-existing warning in `postcss.config.mjs` |
| Frontend build | `PASS` | Compiled successfully; 38 pages generated |
| Targeted Prettier | `PASS` | `All matched files use Prettier code style!` |
| Repository-wide format check | `FAIL` | 18 pre-existing out-of-scope files |
| `contract_diff.py` | `PASS` | Exit 0; 177 backend routes, 108 frontend calls |
| `docs_api_consistency.py` | `PASS` | Exit 0; 30 doc files, 159 documented paths |
| Lighthouse (all six routes) | `PASS` | Accessibility 1.0; best practices 1.0; SEO 1.0; zero failures |
| npm audit / pip-audit | `PASS` / `BLOCKED BY ENVIRONMENT` | Critical-severity gate exits 0; 7 moderate `minimatch`-chain and 1 high `zod` finding remain as documented accepted exceptions. Local OSV/`pip-audit` executables are unavailable. |
| PostgreSQL/Redis/RLS runtime | `BLOCKED BY ENVIRONMENT` / `PASS` | Disposable PG16 binary/connectivity smoke passed but migration-backed fixtures are intentionally unrun; disposable Redis passed 24 targeted tests. Full DB/RLS runtime proof is not established. |

---

## 4. Independent audit loop

- **Round 1 — defects found and fixed:** six in-scope defects (P1 ×3, P2 ×1, P3 ×2) fixed with regressions.
- **Round 2 — clean:** independent full-scope audit reported zero unresolved in-scope P0/P1/P2/P3 defects.
- **Round 3 — clean:** independent full-scope audit reported zero unresolved in-scope P0/P1/P2/P3 defects. These audits predate the final browser-QA code changes.
- **Round 4 — clean after the `use-auth` fix:** independent full-scope audit reported zero unresolved in-scope P0/P1/P2/P3 defects. This audit predates the shared-component contrast fix and final report reconciliation.
- **Round 5 — defects found and fixed:** independent full-scope audit found three P2 defects (final-statement contradiction, audit-loop chronology, `queue(commit=False)` full-session rollback) and one P3 defect (shared-component contrast). All four were fixed with regressions and report corrections.
- **Round 6 — clean on the fixed final tree:** independent full-scope audit verified all four Round 5 fixes and the complete Batch 6 scope with zero unresolved in-scope P0/P1/P2/P3 defects.
- **Round 7 — clean on the fixed final tree:** a second, separate independent full-scope audit confirmed zero unresolved in-scope P0/P1/P2/P3 defects.
- **Loop result: satisfied.** Rounds 6 and 7 are two consecutive independent full-scope audits with zero unresolved in-scope P0/P1/P2/P3 defects on the final code and report tree.

---

## 5. Individually reported backend skipped tests

All 101 skipped tests below are `BLOCKED BY ENVIRONMENT` in the full-suite configuration and none is counted as `PASS`. PostgreSQL skips are due to `PostgreSQL server not reachable` (migration-backed fixtures are intentionally unrun under the protected-artifact constraint); Redis skips are due to `TEST_REDIS_URL is not configured`, with a separate disposable-Redis targeted run used only as scoped evidence.

- `tests/e2e/test_critical_journey.py::test_critical_journey_lead_note_pipeline` — PostgreSQL server not reachable
- `tests/integration/test_auth_concurrency.py::test_password_reset_atomic_claim_concurrency` — PostgreSQL server not reachable
- `tests/integration/test_auth_concurrency.py::test_refresh_token_atomic_rotation` — PostgreSQL server not reachable
- `tests/integration/test_auth_concurrency.py::test_mfa_recovery_code_concurrent_consumption` — PostgreSQL server not reachable
- `tests/integration/test_auth_concurrency.py::test_service_password_reset_single_winner` — PostgreSQL server not reachable
- `tests/integration/test_auth_concurrency.py::test_service_refresh_rotation_revokes_whole_family` — PostgreSQL server not reachable
- `tests/integration/test_auth_concurrency.py::test_service_mfa_recovery_code_single_authentication` — PostgreSQL server not reachable
- `tests/integration/test_database_schema.py::test_per_test_db_connection_preserves_password_auth` — PostgreSQL server not reachable
- `tests/integration/test_database_schema.py::test_compat_roles_bootstrapped_before_migrations` — PostgreSQL server not reachable
- `tests/integration/test_database_schema.py::test_migrations_apply_cleanly` — PostgreSQL server not reachable
- `tests/integration/test_database_schema.py::test_duplicate_email_same_org_rejected` — PostgreSQL server not reachable
- `tests/integration/test_database_schema.py::test_same_email_different_org_allowed` — PostgreSQL server not reachable
- `tests/integration/test_database_schema.py::test_duplicate_phone_vs_whatsapp_rejected` — PostgreSQL server not reachable
- `tests/integration/test_database_schema.py::test_duplicate_website_domain_rejected` — PostgreSQL server not reachable
- `tests/integration/test_database_schema.py::test_invalid_enum_value_rejected` — PostgreSQL server not reachable
- `tests/integration/test_database_schema.py::test_check_constraint_score_range` — PostgreSQL server not reachable
- `tests/integration/test_database_schema.py::test_org_delete_cascades_to_leads` — PostgreSQL server not reachable
- `tests/integration/test_database_schema.py::test_generated_normalized_columns` — PostgreSQL server not reachable
- `tests/integration/test_database_schema.py::test_lead_research_one_to_one` — PostgreSQL server not reachable
- `tests/integration/test_database_schema.py::test_provider_usage_daily_unique` — PostgreSQL server not reachable
- `tests/integration/test_database_schema.py::test_updated_at_trigger_refreshes` — PostgreSQL server not reachable
- `tests/integration/test_database_schema.py::test_migration_0014_schedule_last_fired_additive_idempotent` — PostgreSQL server not reachable
- `tests/integration/test_database_schema.py::test_migration_0015_credential_key_versions_additive_idempotent` — PostgreSQL server not reachable
- `tests/integration/test_database_schema.py::test_migration_0017_automation_hardening_additive_idempotent` — PostgreSQL server not reachable
- `tests/integration/test_database_schema.py::test_migration_0017_idempotency_unique_per_org` — PostgreSQL server not reachable
- `tests/integration/test_database_schema.py::test_migration_0018_phase5d_database_layer_additive_idempotent` — PostgreSQL server not reachable
- `tests/integration/test_database_schema.py::test_retention_chunked_delete_respects_batch` — PostgreSQL server not reachable
- `tests/integration/test_database_schema.py::test_worker_health_retention_prunes_dead_instances` — PostgreSQL server not reachable
- `tests/integration/test_database_schema.py::test_worker_health_constraint_admits_all_worker_types` — PostgreSQL server not reachable
- `tests/integration/test_database_schema.py::test_migration_0019_agent_runtime_additive_idempotent` — PostgreSQL server not reachable
- `tests/integration/test_database_schema.py::test_migration_0019_idempotency_unique_per_org` — PostgreSQL server not reachable
- `tests/integration/test_database_schema.py::test_agent_runs_schema_mirror_matches_0019` — PostgreSQL server not reachable
- `tests/integration/test_database_schema.py::test_all_migrations_immutable_sha256` — PostgreSQL server not reachable
- `tests/integration/test_database_schema.py::test_migration_0018_unchanged_sha256` — PostgreSQL server not reachable
- `tests/integration/test_database_schema.py::test_automation_enum_types_match_schema_contract` — PostgreSQL server not reachable
- `tests/integration/test_database_schema.py::test_automation_enum_replay_is_idempotent` — PostgreSQL server not reachable
- `tests/integration/test_database_schema.py::test_founder_enums_bootstrapped_before_dependent_migrations` — PostgreSQL server not reachable
- `tests/integration/test_database_schema.py::test_enum_bootstrap_covers_uncreated_enums` — PostgreSQL server not reachable
- `tests/integration/test_database_schema.py::test_memory_cleanup_org_scoped_and_working_only` — PostgreSQL server not reachable
- `tests/integration/test_database_schema.py::test_rls_org_isolation_ai_memories_knowledge` — PostgreSQL server not reachable
- `tests/integration/test_database_schema.py::test_users_rls_policy_blocks_self_role_escalation` — PostgreSQL server not reachable
- `tests/integration/test_database_schema.py::test_rls_org_isolation_leads_conversations` — PostgreSQL server not reachable
- `tests/integration/test_database_schema.py::test_migration_0027_m9_intelligence_signals` — PostgreSQL server not reachable
- `tests/integration/test_database_schema.py::test_user_role_enum_binds_by_value_not_name` — PostgreSQL server not reachable
- `tests/integration/test_database_schema.py::test_user_role_pg_enum_labels_match_python_values` — PostgreSQL server not reachable
- `tests/integration/test_database_schema.py::test_datetime_columns_timezone_aware` — PostgreSQL server not reachable
- `tests/integration/test_founder_integration.py::test_chat_persists_messages_without_llm` — PostgreSQL server not reachable
- `tests/integration/test_founder_integration.py::test_propose_and_approve_creates_task` — PostgreSQL server not reachable
- `tests/integration/test_founder_integration.py::test_propose_deny_marks_denied` — PostgreSQL server not reachable
- `tests/integration/test_founder_integration.py::test_expire_due_all_sweeps_expired` — PostgreSQL server not reachable
- `tests/integration/test_founder_integration.py::test_expired_proposal_rejected_at_synchronous_gate` — PostgreSQL server not reachable
- `tests/integration/test_founder_integration.py::test_expired_approval_request_rejected_at_synchronous_gate` — PostgreSQL server not reachable
- `tests/integration/test_m11_ai_run.py::test_ai_run_persists_trace_and_trigger` — PostgreSQL server not reachable
- `tests/integration/test_m11_ai_run.py::test_ai_run_idempotency_key_deduplicates` — PostgreSQL server not reachable
- `tests/integration/test_m11_ai_run.py::test_ai_run_isolated_by_organization` — PostgreSQL server not reachable
- `tests/integration/test_outreach_authorization.py::test_viewer_writes_are_rejected_without_side_effects` — PostgreSQL server not reachable
- `tests/integration/test_outreach_authorization.py::test_viewer_cannot_mutate_existing_rows` — PostgreSQL server not reachable
- `tests/integration/test_outreach_authorization.py::test_authorized_roles_can_write_outreach_records[owner]` — PostgreSQL server not reachable
- `tests/integration/test_outreach_authorization.py::test_authorized_roles_can_write_outreach_records[admin]` — PostgreSQL server not reachable
- `tests/integration/test_outreach_authorization.py::test_authorized_roles_can_write_outreach_records[manager]` — PostgreSQL server not reachable
- `tests/integration/test_outreach_authorization.py::test_authorized_roles_can_write_outreach_records[member]` — PostgreSQL server not reachable
- `tests/integration/test_outreach_authorization.py::test_authorized_roles_can_write_outreach_records[sales_agent]` — PostgreSQL server not reachable
- `tests/integration/test_outreach_authorization.py::test_viewer_keeps_read_access` — PostgreSQL server not reachable
- `tests/integration/test_outreach_authorization.py::test_cross_tenant_updates_are_not_possible[_seed_attempt-/api/v1/outreach/attempts/{id}]` — PostgreSQL server not reachable
- `tests/integration/test_outreach_authorization.py::test_cross_tenant_updates_are_not_possible[_seed_follow_up-/api/v1/outreach/follow-ups/{id}]` — PostgreSQL server not reachable
- `tests/integration/test_outreach_authorization.py::test_cross_tenant_updates_are_not_possible[_seed_manual_task-/api/v1/outreach/manual/{id}]` — PostgreSQL server not reachable
- `tests/integration/test_outreach_authorization.py::test_admin_only_writes_stay_admin_only` — PostgreSQL server not reachable
- `tests/integration/test_resend_cooldown_redis.py::test_two_instances_share_one_window` — TEST_REDIS_URL is not configured
- `tests/integration/test_resend_cooldown_redis.py::test_concurrent_reservations_have_exactly_one_winner` — TEST_REDIS_URL is not configured
- `tests/integration/test_resend_cooldown_redis.py::test_expiry_allows_another_attempt` — TEST_REDIS_URL is not configured
- `tests/integration/test_resend_cooldown_redis.py::test_normalized_forms_share_one_key` — TEST_REDIS_URL is not configured
- `tests/integration/test_resend_cooldown_redis.py::test_redis_keys_never_contain_the_raw_address` — TEST_REDIS_URL is not configured
- `tests/integration/test_resend_cooldown_redis.py::test_unreachable_store_raises_instead_of_failing_open` — TEST_REDIS_URL is not configured
- `tests/integration/test_services_integration.py::test_db_fixture_preserves_password_auth` — PostgreSQL server not reachable
- `tests/integration/test_services_integration.py::test_register_login_refresh_roundtrip` — PostgreSQL server not reachable
- `tests/integration/test_services_integration.py::test_login_wrong_password_rejected` — PostgreSQL server not reachable
- `tests/integration/test_services_integration.py::test_duplicate_email_registration_rejected` — PostgreSQL server not reachable
- `tests/integration/test_services_integration.py::test_lead_lifecycle_and_status_activity` — PostgreSQL server not reachable
- `tests/integration/test_services_integration.py::test_import_worker_parses_and_inserts_leads` — PostgreSQL server not reachable
- `tests/integration/test_services_integration.py::test_import_worker_rejects_invalid_rows` — PostgreSQL server not reachable
- `tests/integration/test_services_integration.py::test_schedule_dispatcher_reserves_and_queues_once` — PostgreSQL server not reachable
- `tests/integration/test_services_integration.py::test_schedule_dispatcher_skips_inactive_workflow` — PostgreSQL server not reachable
- `tests/integration/test_services_integration.py::test_credential_rotate_reencrypts_under_new_key` — PostgreSQL server not reachable
- `tests/integration/test_services_integration.py::test_builtin_workflow_executes_in_process` — PostgreSQL server not reachable
- `tests/integration/test_services_integration.py::test_builtin_workflow_failure_retries_like_other_adapters` — PostgreSQL server not reachable
- `tests/integration/test_services_integration.py::test_process_retries_requeues_due_retrying_rows` — PostgreSQL server not reachable
- `tests/integration/test_services_integration.py::test_process_retries_respects_max_attempts_bound` — PostgreSQL server not reachable
- `tests/integration/test_services_integration.py::test_process_retries_ignores_future_retry_windows` — PostgreSQL server not reachable
- `tests/integration/test_services_integration.py::test_provider_budget_counts_all_org_features` — PostgreSQL server not reachable
- `tests/integration/test_services_integration.py::test_monitoring_aggregates_are_org_scoped` — PostgreSQL server not reachable
- `tests/integration/test_tenant_isolation_rls.py::test_0033_roles_exist_with_expected_attributes` — PostgreSQL server not reachable
- `tests/integration/test_tenant_isolation_rls.py::test_owner_connection_unaffected_without_tenant_context` — PostgreSQL server not reachable
- `tests/integration/test_tenant_isolation_rls.py::test_app_role_sees_nothing_without_tenant_context` — PostgreSQL server not reachable
- `tests/integration/test_tenant_isolation_rls.py::test_app_role_sees_only_guc_tenant` — PostgreSQL server not reachable
- `tests/integration/test_tenant_isolation_rls.py::test_cross_org_insert_rejected_same_org_insert_allowed` — PostgreSQL server not reachable
- `tests/integration/test_tenant_isolation_rls.py::test_cross_org_update_and_delete_are_invisible` — PostgreSQL server not reachable
- `tests/integration/test_tenant_isolation_rls.py::test_worker_role_bypasses_rls_and_sees_all_tenants` — PostgreSQL server not reachable
- `tests/integration/test_tenant_isolation_rls.py::test_definer_lookups_see_through_rls_without_tenant_context` — PostgreSQL server not reachable
- `tests/integration/test_tenant_isolation_rls.py::test_tenant_org_id_semantics` — PostgreSQL server not reachable
- `tests/integration/test_tenant_isolation_rls.py::test_guc_does_not_leak_across_connections` — PostgreSQL server not reachable
- `tests/integration/test_tenant_isolation_rls.py::test_async_auth_flow_enforced_by_rls` — PostgreSQL server not reachable

---

## 6. Evidence references

- `docs/PHASE6_BATCH6_IMPLEMENTATION_PLAN.md`
- `docs/PHASE6_BATCH6_IMPLEMENTATION_REPORT.md`
- `docs/PHASE6_BATCH6_SECURITY_REVIEW.md`
- `docs/PHASE6_BATCH6_FINAL_ACCEPTANCE_REPORT.md`
- `docs/AGENCYOS_PHASE6_DECISION_REGISTER.md`
- Local gate output retained under `C:\Users\awan\AppData\Local\Temp\opencode\`
