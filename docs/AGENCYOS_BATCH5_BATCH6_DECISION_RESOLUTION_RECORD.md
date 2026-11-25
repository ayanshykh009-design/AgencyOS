# AgencyOS Batch 5 + Batch 6 Founder Decision Resolution Record

**Date:** 2026-11-22\
**Repository:** `D:\AgencyOS`\
**Branch:** `feat/phase6-commercial-v1`\
**Committed baseline:** `244e6074fa1e016a7318ab0e011927c93aa178c7`\
**Scope:** D-02, D-18, B6-D-01 through B6-D-05.

This record applies only authorized engineering judgment. It does not invent founder approval, change pricing/legal/retention commitments, weaken tenant isolation or least privilege, or expand V1. Items that require a product/security-boundary or visual-identity choice are explicitly retained as `OPEN — PRODUCTION-ONLY` when they do not block Batch 5/6 acceptance or Batch 7 start.

---

## Disposition summary

| ID | Question | Selected approach | Implementation status | Batch 5/6 acceptance | Batch 7 start | Production launch |
| --- | --- | --- | --- | --- | --- | --- |
| D-02 | `/ai` single-Agent composition | Keep one central Agent and existing Sheet 1-derived visual language | Implemented | Not blocked | Not blocked | `OPEN — PRODUCTION-ONLY` for final visual/product sign-off |
| D-18 | Disabled vs hidden flagged routes | Ship truthful disabled/neutral states; fail closed | Implemented | Not blocked | Not blocked | Resolved under canonical V1; founder override only |
| B6-D-01 | Credential secret entry UX | Keep create/replace disabled with truthful write-only notice | Implemented | Not blocked | Not blocked | `OPEN — PRODUCTION-ONLY` only if UI provisioning becomes a launch requirement |
| B6-D-02 | Approved founder action executor owner | Do not implement `SEND_EMAIL`, `RUN_WORKFLOW`, or `EXPORT` executors | Deferred by design | Not blocked | Not blocked | `OPEN — PRODUCTION-ONLY` if those action types are enabled |
| B6-D-03 | Provider/integration health endpoint | Defer; use existing liveness/readiness and worker health | Deferred | Not blocked | Not blocked | Conditional launch requirement only |
| B6-D-04 | Local-time/per-trigger scheduling | Keep UTC-only with truthful helper text | Implemented | Not blocked | Not blocked | Conditional launch requirement only |
| B6-D-05 | Dead-letter/quarantine and automation rate limits | Defer; keep existing failure states and guarded retry | Deferred | Not blocked | Not blocked | Conditional launch requirement only |

---

## D-02 — `/ai` single-Agent composition

**Original question** (`docs/AGENCYOS_PHASE6_DECISION_REGISTER.md:23-24`): “Which Sheet 1 composition is retained for `/ai`, and how are old multi-agent elements represented?”

**Original options** (`:27-29`): (a) keep Sheet 1 visual language with one Agent; (b) redesign `/ai` layout with owner approval to alter the locked reference.

**Canonical intent:** Blueprint §2.1, §4.2 #25, and D-02 require one central internal Agent, no independent personas, and Sheet 1 visual language.

**Current implementation:** `frontend/src/app/(dashboard)/ai/page.tsx` implements a single lead → goal → run → status/draft → optional dispatch flow. Capability gating is backend-authoritative through `GET /api/v1/ai/capabilities` and `frontend/src/lib/ai-capabilities.ts`. No persona switch or multi-agent UI exists.

**Selected approach:** (a). Preserve the single central Agent and existing shell; make no redesign and add no multi-agent representation.

**Rationale:** This is the only default consistent with the locked product identity and the backend's single agent runtime. It is safe, reversible, and preserves least surprise.

**Rejected alternatives:** Redesigning `/ai`; adding agent personas; representing legacy multi-agent elements as selectable identities.

**Test evidence:** `frontend/src/app/(dashboard)/ai/batch5-ssr.test.tsx`, `frontend/src/lib/ai-capabilities.test.ts`, and Batch 5 final acceptance §6.

**Residual:** Exact Sheet 1 composition sign-off remains a visual/product decision. It does not block engineering acceptance or Batch 7; it is a production-launch gate if final visual approval is required.

---

## D-18 — Feature-flagged routes in V1

**Original question** (`docs/AGENCYOS_PHASE6_DECISION_REGISTER.md:148-149`): whether MFA, verify-email, AI, Founder, Founder Intelligence, and Deliveries routes should ship with truthful disabled states or be hidden until flags are on.

**Original options** (`:152-154`): (a) ship disabled/neutral states; (b) hide routes until enabled.

**Canonical intent:** Blueprint §8.3/§11 requires fail-closed, truthful disabled/unavailable states. Reads may remain available while actions/workers are gated. Production validation requires MFA and email verification; other flags default off.

**Current implementation:** Routes remain visible and render explicit disabled/neutral states. `/ai` uses capability reasons; Founder and Intelligence show truthful disabled actions with reads preserved; Deliveries reports no provider registered; verify-email shows a neutral resend notice; MFA challenges require a real token and backend flag.

**Selected approach:** (a), per canonical V1.

**Rationale:** Hiding core routes would obscure canonical scope; faking availability would be dishonest. The backend remains authoritative and states fail closed.

**Rejected alternatives:** Hiding routes; globally enabling flags; exposing raw flag/environment internals; treating read availability as action availability.

**Test evidence:** `frontend/src/lib/ai-capabilities.test.ts`, `frontend/src/app/(dashboard)/founder/batch5-ssr.test.tsx`, `frontend/src/app/(auth)/auth-ssr.test.tsx`, `frontend/src/services/__tests__/auth.test.ts`, and `frontend/src/app/(dashboard)/batch6-ssr.test.tsx`.

**Residual:** None under canonical V1. A founder override to hide routes would be a product-treatment change, not an engineering blocker.

---

## B6-D-01 — Credential secret entry UX

**Canonical wording** (`docs/PHASE6_BATCH6_IMPLEMENTATION_PLAN.md:365`): “keep backend encrypted-value contract; no plaintext encryption claim.” No separate enumerated question/option list was recorded; the options below are derived only from the canonical row and blueprint, not presented as founder-approved wording.

**Derived question:** What create/replace UX should credentials have when the backend accepts only `encrypted_value` and returns only `value_preview`?

**Derived options:** keep create/replace disabled with a truthful write-only notice; accept plaintext once with a server-side encryption contract change; add client-side encryption and submit `encrypted_value`.

**Canonical intent:** Credentials are admin-only and write-only. V1 may show masked/write-only state; replacement is a separate action. Batch 6 must not claim client-side encryption.

**Current implementation:** `frontend/src/app/(dashboard)/credentials/page.tsx` is admin-only, displays only `value_preview`, keeps New Credential and Replace Value disabled with `CREDENTIAL_WRITE_UNAVAILABLE`, and states values are encrypted server-side with no client-side encryption. Rotate and Delete remain available. `CredentialCreate` requires `encrypted_value` and `value_preview`; responses never include secrets.

**Selected approach:** Keep create/replace disabled with the truthful notice. Do not add a plaintext field or client-encryption claim.

**Rationale:** This preserves the frozen API contract, least privilege, and the server-side secret boundary. It is the safest reversible UX state.

**Rejected alternatives:** Plaintext-once input; client-side “encryption” claim; silently enabling create/replace against the frozen contract; displaying any secret or `encrypted_value` after write.

**Test evidence:** `frontend/src/app/(dashboard)/batch6-ssr.test.tsx:366-393` and `frontend/src/services/__tests__/automation.test.ts` (credential create sends `encrypted_value`; update never patches it).

**Residual:** The plaintext-once versus client-encrypted-value boundary remains a security/product decision only if UI credential provisioning is required for production launch.

---

## B6-D-02 — Approved founder `SEND_EMAIL`/`RUN_WORKFLOW`/`EXPORT` executor owner

**Canonical wording** (`docs/PHASE6_BATCH6_IMPLEMENTATION_PLAN.md:366`): “do not implement in Batch 6.” No separate option list was recorded.

**Derived question:** Which subsystem owns execution of approved founder proposals of type `SEND_EMAIL`, `RUN_WORKFLOW`, and `EXPORT`?

**Derived options:** assign an owner and implement a real executor; keep approval-gated proposals with no downstream side effects.

**Canonical intent:** The approval gate is the deliverable. No subsystem owner was identified; no owner may be invented; no live email, workflow, or export side effect is authorized without a decision.

**Current implementation:** `backend/app/models/enums.py` defines the three action types, but `backend/app/services/founder_action_service.py` only executes `CREATE_TASK`. Other types return a reference noting `handled_by: subsystem` and transition the proposal to `SUCCEEDED`. `backend/app/workers/founder_action_worker.py` only expires stale proposals; it does not execute them.

**Selected approach:** Do not implement any of the three executors. Keep the approval gate with no invented dispatch path.

**Rationale:** Subsystem ownership determines permission propagation, tenant scope, side-effect ownership, idempotency, audit semantics, and whether live SMTP/n8n/export calls occur. Engineering cannot safely select this.

**Rejected alternatives:** Inventing Delivery, Workflow, or Export as owner; reusing admin permissions without review; executing live SMTP/n8n/export calls; treating the `subsystem` note as a real dispatch.

**Test evidence:** `backend/tests/unit/test_founder_unit.py:305-327` and `backend/tests/integration/test_founder_integration.py:175-190` cover real `CREATE_TASK` execution only. No test asserts real email/workflow/export execution.

**Residual:** `OPEN — PRODUCTION-ONLY` if founder assistant action types are enabled. Not a Batch 5/6 or Batch 7 blocker.

---

## B6-D-03 — Provider/integration health endpoint

**Canonical wording** (`docs/PHASE6_BATCH6_IMPLEMENTATION_PLAN.md:367`): “no canonical route; defer.”

**Derived options:** add a new endpoint (outside frozen V1) or defer.

**Current implementation:** `backend/app/api/v1/endpoints/health.py` exposes only liveness/readiness and a hidden alias. `N8nClient.health_check()` exists but is unwired. No provider health UI or canonical route was added.

**Selected approach:** Defer. Use existing infrastructure liveness/readiness and worker health only.

**Rationale:** A provider health endpoint would create a new API contract and require permission and tenant-exposure decisions. It risks leaking provider host/credential state.

**Rejected alternatives:** Exposing n8n `/healthz` through the API; adding a provider-health nav item; showing connectivity badges without a verified endpoint.

**Test evidence:** `backend/tests/api/test_health.py` covers only infrastructure health; Batch 6 implementation report and final acceptance record no provider health endpoint.

**Residual:** Conditional production-launch requirement only if operator provider-health UI is added to launch scope.

---

## B6-D-04 — Local-time/per-trigger scheduling

**Canonical wording** (`docs/PHASE6_BATCH6_IMPLEMENTATION_PLAN.md:368`): “backend is UTC-only; expose truthful UTC helper text, no engine expansion.”

**Derived options:** add local-time/per-trigger timezone support or keep UTC-only with truthful helper text.

**Current implementation:** `frontend/src/app/(dashboard)/triggers/page.tsx` states “Times are shown in UTC” and “UTC only; local-time scheduling is not available.” `backend/app/services/schedule_dispatcher.py` normalizes to UTC. No timezone field or local picker exists.

**Selected approach:** Keep UTC-only and truthful.

**Rationale:** Per-trigger timezone requires storage, DST policy, validation, API/schema changes, and migration work. Client-side conversion presented as scheduling would mislead users.

**Rejected alternatives:** Client-only local display presented as scheduling; adding timezone columns silently; changing cron semantics.

**Test evidence:** `frontend/src/app/(dashboard)/batch6-ssr.test.tsx:290-293` and `backend/tests/unit/test_schedule_dispatcher.py`.

**Residual:** Conditional production-launch requirement only if local-time scheduling is explicitly added to launch scope.

---

## B6-D-05 — Dead-letter/quarantine and automation rate limits

**Canonical wording** (`docs/PHASE6_BATCH6_IMPLEMENTATION_PLAN.md:369`): “not in canonical contract; report deferred, do not silently add.”

**Derived options:** add dead-letter/quarantine state and limiter policy or defer with the gap reported.

**Current implementation:** `DeliveryStatus` has `queued`, `processing`, `delivered`, `retrying`, `failed`, and `cancelled`; no dead-letter or quarantine state exists. `backend/app/core/rate_limit.py` has no automation-specific limiter.

**Selected approach:** Defer. Keep existing failure/cancelled states, manual retry, and guarded execution behavior.

**Rationale:** A dead-letter state changes the persisted state machine and likely requires a migration. Automation-specific rate limits require scopes, thresholds, and failure semantics that cannot be invented under a frozen contract.

**Rejected alternatives:** Adding a new enum/migration silently; applying a generic limiter to automation endpoints without policy; relabeling `failed` as dead-letter without workflow semantics.

**Test evidence:** Frozen plan row `B6-F-09` (INFO/out of contract) and Batch 6 implementation/security reports recording the deferral. No code change, therefore no new regression.

**Residual:** Conditional production-launch requirement only if operational resilience features are added to launch scope.

---

## Overall decision disposition

`PARTIALLY OPEN — NO BATCH 5/6 OR BATCH 7 BLOCKER.`

D-18, B6-D-03, B6-D-04, and B6-D-05 are resolved for canonical V1 by safe engineering defaults. D-02 and B6-D-01 have safe defaults implemented but retain production-only sign-off boundaries. B6-D-02 is genuinely strategic and remains open for production only. None of the seven requires a code change that would expand V1 or weaken authorization, tenant isolation, or least privilege.
