# AgencyOS — Existing Internal Workflow Test Report

## Execution mode

Agent-executed synthetic testing only. A dedicated test organization/account was created per integration test via `AuthService.register` (synthetic data, no real clients). No real external messages were sent. No paid AI calls were made.

## Scenarios

| # | Scenario | Expected | Actual | Result | Evidence |
|---|---|---|---|---|---|
| 1 | Login (valid credentials) | 200 + tokens | 200 + tokens | PASS | `test_services.py::test_login_success_issues_tokens_and_stamps_last_login` |
| 2 | Session bootstrap / refresh | rotated token | rotated token | PASS | `test_services.py::test_refresh_rotates_token` |
| 3 | Logout revokes session | subsequent refresh 401 | 401 | PASS | `test_services.py::test_logout_revokes_all_tokens_and_bumps_token_version` |
| 4 | App navigation / shell | routes resolve | routes resolve | PASS | frontend build + CI |
| 5 | Dashboard data load | 200 aggregates | 200 | PASS | API tests |
| 6 | Create lead | 201 | 201 | PASS | `test_services.py::test_lead_create_sets_defaults` |
| 7 | Update lead | 200 | 200 | PASS | `test_services.py::test_lead_update_to_won_delegates_reconcile` |
| 8 | Retrieve lead detail | 200 | 200 | PASS | `test_services.py` |
| 9 | Tenant boundary | cross-org 404 | 404 | PASS | `test_tenant_isolation_rls.py` |
| 10 | Conversation/activity | persisted | persisted | PASS | `test_services.py` |
| 11 | Create/update outreach attempt | 201/200 | 201/200 | PASS | `test_outreach_authorization.py` (CI) |
| 12 | Create/update follow-up | 201/200 | 201/200 | PASS | `test_outreach_authorization.py` (CI) |
| 13 | Create/update manual task | 201/200 | 201/200 | PASS | `test_outreach_authorization.py` (CI) |
| 14 | VIEWER denied / authorized allowed | 403 for VIEWER, 2xx for others | as expected | PASS | `test_outreach_rbac.py`, `test_leads_rbac.py` |
| 15 | Tasks & notes CRUD | 2xx | 2xx | PASS | `test_task_service.py`, `test_note_service.py` |
| 16 | Calendar | n/a (no provider) | n/a | NOT APPLICABLE | — |
| 17 | Search | 200 results | 200 | PASS | `test_search_service.py` |
| 18 | File upload/read | 2xx | 2xx | PASS (unit/API) | upload endpoints + tests |
| 19 | Notifications | 2xx | 2xx | PASS | `test_phase5d_services.py` |
| 20 | Report data vs seeded records | consistent | consistent | PASS | growth/intelligence tests |
| 21 | AI Assistant (safe) | flag-gated | flag-gated (OFF) | NOT APPLICABLE (disabled by default) | — |
| 22 | Automation screens (no unsafe triggers) | read-only status | read-only status | PASS | `test_automation_api.py` |

## Synthetic vs actual

- All agent tests used synthetic data in disposable databases.
- Actual owner business usage (real leads, real inbox) is NOT covered by this audit; see the owner runbook.

## Remaining owner-operated scenarios

- Real SMTP delivery (requires owner-provisioned SMTP).
- Real n8n workflow execution (requires `N8N_BASE_URL`).
- Real LLM provider calls (requires API keys + positive budgets).
- Browser-level UX validation (loading/empty states) — owner should run the runbook.
