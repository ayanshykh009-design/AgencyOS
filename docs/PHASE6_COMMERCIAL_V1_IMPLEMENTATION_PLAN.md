# AgencyOS Phase 6 — Commercial V1 Implementation Plan

Baseline branch: `feat/phase6-commercial-v1`  
Baseline SHA: `5c584de850b8bbe6e16900248897e52d8fef19dc`  
Scope: 37 canonical routes.

## 1. Architecture
- Reuse existing Next.js/React/Tailwind/React Query/Zod stack.
- Backend remains authority for auth, permissions, tenant isolation, and feature availability.
- No billing, public chatbot, generic approvals, memory, AI runs, developer portal, workflow builder, task board, monitoring logs, mark-all-read, appearance persistence, or fake submission success.

## 2. Security Remediation First
- `POST /api/v1/pipeline/leads/{lead_id}/stage`: add `Permission.LEAD_WRITE`.
- Conversations: add `LEAD_READ`/`LEAD_WRITE`; verify lead belongs to org; make sender attribution server-authoritative.
- Frontend: tenant/session-aware query cache; clear on logout/principal change.
- Credentials remain write-only and admin-only.
- Contact/Demo submissions remain disabled until safe backend.

## 3. Route Inventory
37 canonical routes as defined in the Master Blueprint. Preserve legacy redirects:
- `/settings/security` -> `/settings/account`
- `/operational-monitoring` -> `/monitoring`
- `/worker-monitoring` -> `/monitoring`

## 4. Implementation Batches
1. Security remediation + frontend foundation.
2. Public + authentication.
3. Workspace + CRM (including conversations).
4. Management + monitoring.
5. AI + Founder.
6. Automation.
7. Brand integration.

> Owner note (Batch 1 execution): the founder-directed Batch 1 covers the five
> public marketing routes `/pricing`, `/contact`, `/demo`, `/terms`, `/privacy`
> (Sheet 2A screens 01–05) as the first implemented slice of "Public +
> authentication". Status recorded in section 9.

## 5. API Integration
Use only verified endpoints. Reuse existing services and wrappers. Add missing wrappers: register, conversations, assignment history, monitoring delivery-stats, auth changePassword.

## 6. Tests
- Backend RBAC and tenant tests.
- Frontend unit/API/component tests.
- Typecheck, lint, production build.
- Responsive/accessibility checks.

## 7. Acceptance
- All 37 routes work within supported scope.
- Real backend integration only.
- Correct permissions and tenant isolation.
- Truthful unavailable states.
- Passing available tests and build.

## 8. Deferred
- Contact/Demo submission.
- Task Board.
- Monitoring Logs.
- Appearance persistence.
- 3D Core Orbit GLB until approved asset available.

## 9. Batch Status

### Batch 1 — Public marketing (5 routes) — COMPLETE 2026-11-11

Implemented exactly the five authorized routes; no other pages changed.

**Files added**
- `frontend/src/app/(marketing)/layout.tsx` — public shell (header + footer, dark-first).
- `frontend/src/app/(marketing)/pricing/page.tsx` — Sheet 2A screen 01.
- `frontend/src/app/(marketing)/contact/page.tsx` — Sheet 2A screen 02.
- `frontend/src/app/(marketing)/demo/page.tsx` — Sheet 2A screen 03.
- `frontend/src/app/(marketing)/terms/page.tsx` — Sheet 2A screen 04.
- `frontend/src/app/(marketing)/privacy/page.tsx` — Sheet 2A screen 05.
- `frontend/src/components/marketing/core-orbit.tsx` — static SVG Core Orbit mark.
- `frontend/src/components/marketing/public-header.tsx` — public nav (desktop + mobile menu).
- `frontend/src/components/marketing/public-footer.tsx`.
- `frontend/src/components/marketing/plan-card.tsx`.
- `frontend/src/components/marketing/comparison-table.tsx`.
- `frontend/src/components/marketing/faq-list.tsx` — accessible disclosure row.
- `frontend/src/components/marketing/form-fields.tsx` — dark field primitives (Field/TextInput/SelectInput/TextAreaInput).
- `frontend/src/components/marketing/legal-page.tsx` — shared legal layout family.
- `frontend/src/components/marketing/legal-toc.tsx` — "On this page" TOC (IntersectionObserver).
- `frontend/src/components/marketing/unavailable-note.tsx` — amber unavailable-state note.
- `frontend/src/lib/marketing.ts` — static content data (plans, comparison, FAQ, options, legal outlines).
- `frontend/src/lib/marketing.test.ts` — 16 content-integrity tests.
- `frontend/src/lib/validation/marketing.ts` — Zod schemas for contact/demo forms (client-side validation only).
- `frontend/src/lib/validation/marketing.test.ts` — 7 schema tests.

**Files modified**
- `frontend/tailwind.config.ts` — approved design tokens (printed neutral + semantic values, font stacks with the specified fallbacks).
- `frontend/src/app/globals.css` — reduced-motion-aware smooth anchor scrolling.
- `frontend/src/lib/constants.ts` — added `pricing`, `contact`, `demo`, `terms`, `privacy` routes.

**Verification executed (frontend, 2026-11-11)**
- `npm run typecheck` — pass.
- `npm test` — 27 files / 170 tests pass (includes the 23 new Batch 1 tests).
- `npm run lint` — 0 errors; 1 pre-existing warning (`postcss.config.mjs`, untouched file).
- `npm run build` — production build passes; `/pricing`, `/contact`, `/demo`, `/terms`, `/privacy` all present.
- In-browser visual verification (dev server, 742px viewport and scaled 1440px desktop render): all five pages checked against the PDF screens; FAQ accordion, mobile menu, and inline validation verified working.

**Honest-state decisions (documented deviations)**
- Contact/Demo submit controls are rendered per the design but disabled, with an amber "no public backend yet" note; no data is transmitted, `/webhooks/leads` is never referenced, and no success state is ever shown. The PDF's "FEEDBACK STATES" reference panels are therefore not rendered live (they cannot legitimately occur without a backend).
- Pricing keeps "Contact for pricing" everywhere; CTAs route only to `/contact` or `/demo`; FAQ answers avoid invented prices/limits/guarantees.
- Header items Product/Solutions/Resources/Company render as non-interactive placeholders (no approved destinations exist; no broken links).
- Sheet 1 (page 1 of the PDF) is a raster/vector board that the built-in viewer could not render; it was inspected via a pdf.js render and used for brand identity. Legal text remains owner-supplied placeholders with the amber draft notice, per the design annotation.

**Not in scope / untouched**
- Home `/`, auth pages, dashboard, CRM, AI, automation, monitoring pages, backend security files (pipeline/conversations edits from the earlier authorized security batch remain unstaged), `database/migrations/0016_search_trigram_indexes.sql`.

---

### Batch 2 — Authentication (5 routes) — COMPLETE 2026-11-11

Implemented exactly the five authorized routes on `feat/phase6-commercial-v1`; the five Batch 1 pages, Home `/`, `/reset-password` and `/invite/[token]` were not modified.

**Files added**
- `frontend/src/app/(auth)/signup/page.tsx` — Sheet 2A screen 06.
- `frontend/src/components/auth/auth-shell.tsx` — dark-first scene: obsidian backdrop, ambient glow, Core Orbit artwork (two static tilted orbits + slow 120 s dashed comet ring; reduced-motion disables it), wordmark, centred card.
- `frontend/src/components/auth/password-input.tsx` — password field with visibility toggle (Sheet 1 login design).
- `frontend/src/components/auth/code-boxes.tsx` — six single-digit code boxes (Sheet 2A screen 09): auto-advance, backspace navigation, full-code paste, red invalid state.
- `frontend/src/lib/validation/auth.ts` — Zod schemas mirroring the backend constraints (password 8–128; names ≤255; slug `^[a-z0-9][a-z0-9-]*$` ≤63) + `slugifyOrganization`.
- `frontend/src/lib/validation/auth.test.ts` — 16 schema/util tests.

**Files modified**
- `frontend/src/app/(auth)/login/page.tsx` — restyled to the dark-first identity (Sheet 1 screen 02): business email, password + visibility toggle, backend error states (invalid credentials, too many attempts, email-verification gate with link), MFA hand-off preserved (`auth.mfa_required` → `/mfa?token=…`), session set HttpOnly-cookie/in-memory exactly as before.
- `frontend/src/app/(auth)/mfa/page.tsx` — restyled (Sheet 2A screen 09): six-digit boxes (TOTP), invalid-code red state ("That code did not work. Try again."), recovery-code mode (the existing factor the backend issues/accepts at activation; no other recovery flow invented), TOTP-only info badge, back-to-sign-in.
- `frontend/src/app/(auth)/verify-email/page.tsx` — restyled (Sheet 2A screen 10): verifying / verified / expired-invalid / pending states; resend with enumeration-safe neutral confirmation ("If an account exists…"), 202 always; neutral disabled state shown only when the backend reports email verification is disabled. Verified state only after a real 204.
- `frontend/src/app/(auth)/forgot-password/page.tsx` — restyled (Sheet 2A screen 11): generic enumeration-safe confirmation required by the spec ("If an account exists for that address, a reset link is on its way."); neutral disabled state when the backend reports `PASSWORD_RESET_ENABLED` off; removed the silent success-on-network-error path.
- `frontend/src/services/auth.ts` — added `register()` wrapper (POST /auth/register; persists session like login; organization + OWNER created server-side) and the disabled-state signal helpers (`isPasswordResetDisabled`, `isEmailVerificationDisabled`) driven by the exact `detail` strings the backend returns when the flags are off.
- `frontend/src/services/__tests__/auth.test.ts` — added register (success/conflict/no-bearer), mfaVerify persistence/no-bearer, browser-storage token-leak guard, and disabled-signal helper tests.
- `frontend/src/lib/constants.ts` — added `signup: "/signup"`.
- `frontend/src/app/globals.css` — added `agencyos-orbit-spin` keyframes + `.auth-orbit` (animation disabled under `prefers-reduced-motion: reduce`).
- `docs/PHASE6_COMMERCIAL_V1_IMPLEMENTATION_PLAN.md` — this section.

**API integration (real endpoints only)**
- `POST /auth/register` (201) — full_name / organization_name / organization_slug; backend creates Organization + OWNER user atomically, tenant isolation, `RATE_LIMIT_STRICT`, refresh cookie set; optional `email_verification_required` flag honoured (redirects to `/verify-email?registered=1`; otherwise dashboard).
- `POST /auth/login`, `POST /auth/refresh`, `GET /auth/me`, `POST /auth/logout`, `POST /auth/mfa/verify` — unchanged contracts; HttpOnly refresh cookie + in-memory access token preserved; no token ever written to browser storage (guarded by test).
- `POST /auth/verify-email` (204 after real consumption), `POST /auth/verify-email/resend` (always 202; enumeration-safe; disabled → exact "Email verification is not enabled" detail).
- `POST /auth/password-reset/request` (always 202; disabled → exact "Password reset is not enabled" detail). `/reset-password` intentionally NOT implemented in this batch.

**Verification executed (2026-11-11)**
- `npm run typecheck` — pass. `npm run lint` — 0 errors (1 pre-existing warning, `postcss.config.mjs`). `npm test` — 28 files / 191 tests pass (21 new: 16 validation + 5 service). `npm run build` — pass; 37 pages; `/login`, `/signup`, `/mfa`, `/verify-email`, `/forgot-password` all present.
- Prerendered HTML inspected via `curl` against `next start` (login/signup/forgot-password contain full content; `/mfa` and `/verify-email` are Suspense-wrapped `useSearchParams` pages and render a loading shell until hydration — fallback improved from `null` to a visible skeleton).
- **Visual desktop/mobile inspection against the PDF was NOT executed**: the in-app browser was unavailable in this session (tab capture requires a visible desktop window). Layout/markup was verified structurally only.

**Documented deviations (design vs. honest behavior)**
- Sheet 1 login artwork shows social sign-in buttons and a "Remember me" checkbox. Neither is implemented: there is no OAuth backend (and social sign-in is explicitly out of scope for V1), and "Remember me" would require a session-model change the batch does not authorize. Email + password only.
- Sheet 2A screen 06 annotations show the social-free "Email and password only. No social sign-in" note — fully honoured.
- Sheet 2A screens 09/10/11 render their "annotation" bars (e.g. "Authenticator (TOTP) only", feature-flag notes) as live, minimal UI elements or real backend-driven states; annotation chrome itself is not rendered.
- `/verify-email` pending/expired states embed a resend form with an email input — the design shows a resend button alone, but the real API requires an address; the form is the minimum honest wiring.
- Slug field auto-derives from workspace name until the user edits it; backend pattern mirrored exactly (client never stricter than the API).
- No onboarding routes were created. **Onboarding integration requirements for a later batch:** Sheet 2A screens 03/04 (onboarding 1/4–2/4), 07 (Team) and 08 (AI preferences) are designed but not implemented. Registration covers onboarding step 1. Step 2 (Business Profile: industry/size/goal/target/website/currency) has no backend model or endpoint as far as this batch's read-only audit found; steps 3–4 would need audited wiring to existing team/AI endpoints plus any missing profile persistence. A dedicated backend audit and founder scope decision are required before these screens are implemented.
- Design reference: AGENCYOS_ALL_IN_ONE.pdf (Sheet 1 brand board/login, Sheet 2A screens 06/09/10/11, Sheet 2C components, exact printed tokens). The 3D Core Orbit render asset remains unavailable; the SVG Core Orbit from Batch 1 is reused.