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
- `frontend/src/lib/marketing.test.ts` — 17 content-integrity tests.
- `frontend/src/lib/validation/marketing.ts` — Zod schemas for contact/demo forms (client-side validation only).
- `frontend/src/lib/validation/marketing.test.ts` — 8 schema tests.

**Files modified**
- `frontend/tailwind.config.ts` — approved design tokens (printed neutral + semantic values, font stacks with the specified fallbacks).
- `frontend/src/app/globals.css` — reduced-motion-aware smooth anchor scrolling.
- `frontend/src/lib/constants.ts` — added `pricing`, `contact`, `demo`, `terms`, `privacy` routes.

**Verification executed (frontend, 2026-11-11)**
- `npm run typecheck` — pass.
- `npm test` — 27 files / 170 tests pass (includes the 25 new Batch 1 tests).
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