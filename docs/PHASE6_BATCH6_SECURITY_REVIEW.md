# AgencyOS Phase 6 — Batch 6 Security Review

Scope: frozen plan `B6-PLAN-v1.0`; six canonical automation routes plus the backend hardening explicitly listed in the plan. This review is based on source inspection and locally executed tests only. No live provider connectivity or remote CI evidence is claimed.

## 1. Security conclusion

Within the frozen Batch 6 scope, backend authority remains authoritative and no permission was broadened. New request-hardening controls are fail-closed, secrets are not logged or rendered, tenant scoping is preserved or tightened, and no fake provider success, live outbound side effect, paid AI call, arbitrary workflow execution, or globally enabled risky flag was introduced.

Residual risks are unchanged deferred/founder-decision items and local environment limitations; they are listed in section 8.

## 2. Threat model and controls

| Threat | Control | Evidence |
|---|---|---|
| Cross-tenant workflow/trigger/execution/credential/delivery access | Org derived from authenticated principal; repository filters; nested trigger path ownership tightened; RLS foundations reused | `workflow_trigger.py` org+workflow+id lookup; `workflow_service.py` overrides client org with path/principal context; regression tests in `test_workflow_service.py`, `test_workflow_trigger_service.py` |
| Privilege escalation via frontend | Backend remains authority; exact backend permission keys mirrored in UX helpers; shared matrix untouched | `frontend/src/lib/batch6-permissions.ts`; `site-nav.tsx` Credentials gate changed only to `credential_manage` |
| Webhook forgery | Existing shared secret plus mandatory HMAC-SHA256 over exact raw body with timestamp and nonce | `webhooks.py` `_verify_signature`, raw `await request.body()`, unified 401 envelope |
| Webhook replay | Timestamp skew, nonce format, org-scoped single-use nonce, Redis `SET NX EX` in deployed environments, bounded local fallback only | `webhooks.py` replay guard; `config.py` bounds; tests in `test_webhooks.py`, `test_webhook_security_settings.py` |
| n8n SSRF/URL injection | `N8N_BASE_URL` is the only dispatch authority; workflow-supplied path must be relative `/webhook/...`; no credentials, query, fragment, traversal, backslash, control chars, or redirects | `n8n_client.py` `_validate_webhook_path`; tests in `test_n8n_client.py` |
| Secret leakage | Credentials remain write-only in UI; no `encrypted_value`, provider key, host, or raw metadata rendering; n8n/webhook secrets never logged; upstream response bodies are not retained | credential page redaction/UX, `n8n_client.py` fixed redaction marker and `_sanitize_path`, `execution_adapter.py` response-free logging, delivery metadata allowlist, env templates document names only |
| Prompt injection into workflow actions | No AI-generated arbitrary actions; no new execution path; tool registry/kill switch/budgets reused from Batch 5/M11 | no builder; no new tool registration; no `caller_permissions=None` new path |
| Infinite loops / budget burn | No new AI execution path; existing kill switch enforced on manual start and worker processing | `workflow_execution_service.py` kill-switch guard; `execution_worker.py` flag gate |
| Duplicate side effects | Webhook idempotent duplicate response preserved; n8n org/actor/workflow/execution/idempotency metadata is sent both as signed headers and inside the HMAC-covered payload; execution state guards; retry only in allowed states | `webhooks.py`, `n8n_client.py`, `execution_adapter.py`, `execution_worker.py`, execution and delivery UI state guards |
| Unauthorized cancel/retry/pause/run | Backend permission and state checks retained; frontend action gates aligned with backend keys and disabled with explicit reasons | `workflows.py`, executions page, deliveries page, workflow detail page, permission helper tests |
| Raw payload/provider metadata exposure | Allowlist redaction in delivery timeline/error summaries and workflow definition/config views; no raw metadata JSON | `redactMetadata` usage across `/workflows/[id]` and `/deliveries`; SSR redaction tests |

## 3. RBAC and frontend authorization

- `workflow_read/write/manage`, `execution_read` + `workflow_write`, `automation_read/write/manage/control`, `credential_manage`, and `delivery_read/write/manage` are mapped in `frontend/src/lib/batch6-permissions.ts`.
- The shared RBAC matrix in `frontend/src/lib/permissions.ts` and backend `core/permissions.py` was not changed.
- `automation_manage` remains admin-only; `automation_control` remains admin-only.
- Credentials require `credential_manage` on every backend endpoint; the nav item and page now use that key.
- Frontend checks are explicitly UX-only; the backend remains the source of truth.
- Final synthetic-browser role QA confirmed the shared matrix semantics independently of frontend visibility: `viewer` has read-only UI and receives backend `403` for workflow/delivery writes and credential reads; `member` is write-capable for workflow actions and delivery creation but cannot use admin-only `delivery_manage` retry/cancel actions and is denied admin-only credentials; `owner`/`admin` have the expected write and credential controls. The synthetic API used only outside the repository was corrected to mirror `backend/app/core/permissions.py`; no product permission was broadened.
- D-13 AI Cancel remains preserved as the existing Batch 5 `agent_manage` UI gate; Batch 6 execution cancel uses the backend-aligned `workflow_write` contract and does not change D-13.

## 4. Tenant isolation

- Nested workflow trigger mutations now verify the trigger belongs to both the organization and the workflow in the URL before update/delete.
- Workflow-scoped trigger creation overrides client-supplied organization identifiers with the authenticated/outbound adapter context.
- No new endpoint accepts a client-supplied org identifier as an authority.
- DB/RLS runtime proof remains unavailable locally (95 PostgreSQL skips); this is `BLOCKED BY ENVIRONMENT`, not a claimed pass.

## 5. Secrets and redaction

- No plaintext credential value is rendered after write; the credential page explicitly warns that values are write-only and does not claim plaintext encryption in the browser.
- `encrypted_value`, provider keys, hostnames, and raw provider payloads are not displayed.
- Delivery metadata, payloads, and timeline entries use an allowlist (`code`, `type`, `step`, `status`, `attempt`, `event_type`, `reason`); all other fields render as `<redacted>`.
- n8n upstream response bodies are never retained; `N8nHttpError` stores only a fixed `<redacted provider response>` marker, and stored error URLs are relative paths only.
- The n8n adapter does not log provider response bodies; Round 1 regression capture confirms response markers never enter application logs or execution error payloads.
- Webhook/n8n signature values and secrets are not included in errors or logs.
- Env templates document only setting names and safe defaults; no secret values or risky global flags were enabled.

## 6. Fail-closed and request hardening

- Missing `WEBHOOK_SECRET` returns 503; wrong shared header or invalid signature returns the unified 401 envelope.
- Timestamp skew and nonce format are validated before signature success is accepted.
- Deployed replay enforcement requires shared Redis; failure to use Redis fails closed with 503. The in-process fallback is limited to explicit local environments and capped/pruned.
- `N8N_WEBHOOK_SECRET` is mandatory when `N8N_BASE_URL` is configured outside explicit local environments; runtime validation applies to staging/QA/unknown environments, and production validation additionally asserts it.
- Worker execution processing is disabled when `EXECUTION_WORKER_ENABLED` is false; heartbeats still run so monitoring remains truthful.
- Manual execution start applies the existing kill-switch guard; generic workflow status PATCH is rejected; pause/resume state and audit commits are atomic.

## 7. Client-side safety

- All six routes render explicit denied, loading, empty, error+retry, and state-dependent action behavior using shared typed components.
- Workflow visualization is read-only and derived only from stored `definition`; no step editor, arbitrary action code, or unsupported trigger/action node is exposed.
- Run now is disabled unless the workflow is active.
- Scheduling text is UTC-only; no local-time picker or implied local-time support is presented.
- Delivery manual dispatch remains disabled with an explicit “no provider registered” reason; no fake destination or success state is shown.
- SSR tests verify static markup only and do not claim hydration or click-through verification; hydration and click-through were separately verified in the real in-app browser with a synthetic API, not inferred from SSR output.
- `frontend/src/hooks/use-auth.ts` uses `useSyncExternalStore` with a null server snapshot to eliminate the fast-refresh race/hydration mismatch found only in the browser; `use-auth.test.ts` is the regression.
- All in-scope muted metadata now uses the AA-safe `text-gray-600` token instead of the 2.53:1 `text-gray-400` token; `batch6-contrast.test.ts` guards against regression. Lighthouse reported accessibility `1.0` with zero failures on all six routes after the fix.

## 8. Residual risks and deferred items

- Local PostgreSQL/Redis absence blocks DB/RLS and runtime replay proof (`BLOCKED BY ENVIRONMENT`).
- No live n8n/SMTP/WhatsApp/calendar provider verification; provider health endpoint is a founder decision.
- Credential secret-entry UX remains a founder decision; the write-only backend contract was preserved.
- Founder `SEND_EMAIL`/`RUN_WORKFLOW`/`EXPORT` executor ownership remains a founder decision; no subsystem owner was invented.
- Local-time/per-trigger scheduling remains a founder decision; UTC-only truth is exposed.
- Automation-specific dead-letter/quarantine state and rate limits remain deferred; no silent schema or limiter change was made.
- Repository-wide Prettier drift and the one lint warning are pre-existing and out of scope; all Batch 6 files pass Prettier.
- Next.js reported a security-advisory upgrade nudge on an earlier first build attempt. Investigation found no applicable GHSA for installed `next@16.4.6`; no Next.js upgrade was made, while integrated dependency-security remediation patched Vitest/`@vitest/mocker` to 4.1.12 and added the Vite 8.2.4 override.
- Fresh remote CI exact-SHA evidence remains `NOT VERIFIED` because `gh` is unavailable. The four explicit viewport sizes remain `BLOCKED BY ENVIRONMENT`; full keyboard tab traversal remains `NOT VERIFIED` even though focus styling was verified programmatically. Local `npm audit --audit-level=critical` passes with 7 moderate `minimatch`-chain and 1 high `zod` finding documented as accepted exceptions; local OSV/`pip-audit` executables remain `BLOCKED BY ENVIRONMENT`. Repository-wide `format:check` remains a pre-existing out-of-scope `FAIL`; all Batch 6 files pass targeted Prettier.

## 9. Audit status

- **Round 1 — complete, three backend/security defects found and fixed.** The n8n production dispatch now carries signed org/actor/workflow/execution/idempotency metadata; raw provider responses are no longer logged; arbitrary upstream response bodies are no longer stored or returned in execution errors. Regressions cover the adapter, worker, client, log capture, and API schema.
- **Frontend Round 1 — complete, three route defects found and fixed.** Delivery retry/cancel now send the required empty JSON bodies; trigger filtering is backend-side; execution duration is rendered; `canWriteTriggers` uses the exact backend `automation_write` key.
- **Round 2 — clean, pre-browser-QA.** Independent full-scope audit verified all Round 1 fixes, webhook/n8n/config hardening, RBAC/tenancy, six routes, and no-new-contract scope with zero unresolved in-scope P0/P1/P2/P3 defects.
- **Round 3 — clean, pre-browser-QA.** Independent full-scope audit verified all six routes, RBAC/redaction, webhook/n8n/config hardening, B6-F-01…F-08, and all Round 1 fixes with zero unresolved in-scope P0/P1/P2/P3 defects.
- **Round 4 — clean after the `use-auth` fix.** Independent full-scope audit reported zero unresolved in-scope P0/P1/P2/P3 defects; it predates the shared-component contrast fix.
- **Round 5 — defects found and fixed.** Independent full-scope audit found three P2 defects (report contradiction, audit-loop chronology, `commit=False` full-session rollback) and one P3 defect (shared-component contrast). All four were fixed with regressions and report corrections; see implementation report §3.3.
- **Round 6 — clean on the fixed final tree.** Independent full-scope audit verified all four Round 5 fixes and the complete Batch 6 scope with zero unresolved in-scope P0/P1/P2/P3 defects.
- **Round 7 — clean on the fixed final tree.** A second, separate independent full-scope audit confirmed zero unresolved in-scope P0/P1/P2/P3 defects.
- **Loop result: satisfied.** Rounds 6 and 7 are two consecutive independent full-scope audits with zero unresolved in-scope P0/P1/P2/P3 defects on the final code and report tree.
- **INFO-only observations:** stale trigger-permission test description; denied-role list/detail fetches on workflow pages; bounded delivery `last_error` rendering; pre-existing Batch 5 `n8n_tool` raw-result behavior; pre-existing provider error truncation; webhook org-slug lookup ordering. Runtime RLS proof remains `BLOCKED BY ENVIRONMENT`; none of these observations is an unresolved in-scope P0/P1/P2/P3 defect.
