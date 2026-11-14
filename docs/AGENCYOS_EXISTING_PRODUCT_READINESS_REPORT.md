# AgencyOS — Existing Product Readiness

## Method

Inspection of `frontend/src/app` and `backend/app/api/v1/endpoints` plus existing test suites. No new feature code was written. Browser-level E2E was not executed locally; claims are based on source inspection and the passing CI suite (frontend lint/typecheck/tests/build all green on merge commit `e020aae`).

## Surface classification

| Surface | Status | Evidence / notes |
|---|---|---|
| App shell / navigation | Implemented | `frontend/src/app` layout + sidebar; protected routes via auth context. |
| Auth (login/register/refresh/logout) | Complete & tested | `test_services.py`, `test_refresh_cookie.py`, `test_auth_resend.py`; session bootstrap covered. |
| Dashboard | Implemented, data-backed | Aggregate endpoints exist; covered by API tests. |
| CRM / leads | Complete & tested | `test_leads_rbac.py`, `test_services.py`, `test_lead_service` (unit). H2-style RBAC verified. |
| Conversations / activity | Implemented & tested | `test_services.py` (reopen on lead message, agent message). |
| Outreach (messages/attempts/follow-ups/manual) | Complete & tested | H2-secured writes; `test_outreach_rbac.py`, `test_outreach_authorization.py`. |
| Notes | Complete & tested | `test_note_service.py`. |
| Tasks | Complete & tested | `test_task_service.py`. |
| Calendar | Partial / deferred | Task due dates exist; no external calendar provider. |
| Files | Implemented (local storage) | `UPLOAD_DIR`, upload endpoints; no object storage by default. |
| Search | Implemented & tested | `test_search_service.py`. |
| Notifications | Implemented (in-app) | `test_phase5d_services.py` (notification read/set-read). |
| Reports / analytics | Implemented | Growth/intelligence endpoints; covered by API tests. |
| Settings / account | Implemented | user/team/invite flows tested (`test_team_service.py`). |
| Approvals / governance | Implemented (flag-gated) | `APPROVAL_EXPIRY_HOURS`; services tested. |
| AI Assistant / Brain | Implemented (flag-gated) | `AGENT_RUNTIME_ENABLED=false` by default; services and tools tested. |
| Integrations / automation screens | Implemented (config-gated) | n8n client tested; provider layer tested. |
| Pipeline (Kanban/stages) | Implemented & tested | `test_pipeline_service.py`. |

## Defects found during this audit

- **P1 (fixed in H2 commit):** Outreach attempt/follow-up/manual write endpoints lacked authorization → fixed via `LEAD_WRITE` (H2).
- **P1 (fixed in H2 commit):** `OutreachService.update_*` did not refresh after commit, causing `MissingGreenlet`/500 on update responses → fixed via `session.refresh(...)` (mirroring `LeadService`).
- No other P0/P1 defects reproduced in the existing unit/integration suites (1870 passed in CI).

## Permission-denied behavior

- VIEWER receives 403 on all write routes for leads, outreach, deliveries, exports, automation, credentials, etc. (verified by `test_*_rbac.py` suites).
- Admin-only surfaces (messages, lead-sources, pipeline manage, automation control, credentials manage) return 403 for non-admin (verified).

## Tenant isolation

- RLS policies on all org-scoped tables; `activate_org` GUC propagation tested (`test_tenant_context.py`, `test_tenant_isolation_rls.py`).
- Cross-tenant reads/writes return 404/not-found (verified in integration tests).

## Empty/loading/error states

- Backend returns structured error envelope (`{"error":{"code","message","details"?}}`) consistently; frontend API client surfaces errors. Detailed per-page empty-state audit is a manual UX task; no broken-data-path defects found in tests.

## Verdict

Existing product is functionally complete for the implemented (non-Phase-6) surfaces, with two P1 defects fixed in the H2 commit. No P0 defect remains. Feature flags keep unshipped subsystems fail-closed.
