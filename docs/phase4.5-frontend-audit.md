# Phase 4.5 — Frontend Audit

Audit of the AgencyOS Next.js frontend for production readiness: build gates,
route/permission coverage, session handling, environment validation, security
headers, and gaps. Conducted as part of Phase 4.5 Production Readiness.

## Scope

| Concern             | Location                                    | Status |
| ------------------- | ------------------------------------------- | ------ |
| Lint                | `npm run lint` (ESLint)                     | ✅ PASS (0 errors, 1 pre-existing warning) |
| Type check          | `npm run typecheck` (`tsc --noEmit`)        | ✅ PASS |
| Formatting          | `npm run format:check` (Prettier)           | ✅ PASS |
| Tests               | `npm test` (Vitest)                         | ✅ PASS (12 files, 68 tests) |
| Env validation      | `frontend/src/lib/env.ts` (zod)             | ✅ PASS |
| Security headers    | `frontend/next.config.mjs`                  | ✅ PASS |
| Session storage     | `frontend/src/lib/session.ts`               | ✅ PASS (with residual risk, below) |
| RBAC mirror         | `frontend/src/lib/permissions.ts`           | ✅ PASS (in sync with backend) |
| Route gating        | `frontend/src/app/**/page.tsx`              | ✅ PASS |
| Invite accept page  | `frontend/src/app/`                         | ⚠️ GAP (documented) |

## Gate Results

### Lint — `npm run lint`

0 errors. One pre-existing warning in `postcss.config.mjs` (anonymous default
export) that does not block the build.

### Type Check — `npm run typecheck`

Clean. `UserRole` union in `frontend/src/types/index.ts`
(`"owner" | "admin" | "manager" | "member" | "sales_agent" | "viewer"`) matches
the backend `UserRole` StrEnum exactly (6 values, same spellings).

### Formatting — `npm run format:check`

All matched files use Prettier code style.

### Tests — `npm test`

12 files, 68 tests passing:

| Test file | Tests | Coverage |
| --------- | ----- | -------- |
| `api-client.test.ts` | 7 | fetch wrapper, error envelope, auth headers |
| `session.test.ts` | 5 | localStorage + middleware cookie lifecycle |
| `permissions.test.ts` | 4 | RBAC matrix (lead/task/note, admin- and manager-gated) |
| `utils.test.ts` | 2 | helpers |
| `auth.test.ts` | 3 | login/logout/fetch-current-user services |
| `leads.test.ts` | 8 | list/get/create/update/delete/assign services |
| `pipeline.test.ts` | 6 | stages, close reasons, stage moves |
| `tasks.test.ts` | 6 | CRUD, complete, reminders |
| `notes-search-audit.test.ts` | 6 | notes CRUD, search, audit read |
| `teams-users-assignment.test.ts` | 12 | invites, role updates, assignment rules |
| `exports.test.ts` | 4 | CSV export download |
| `ai.test.ts` | 5 | tools manifest, brain run, dispatch, settings |

## Route Coverage

All 10 dashboard surfaces have pages:

| Route | Page | Backend gate |
| ----- | ---- | ------------ |
| `/dashboard` | `dashboard/page.tsx` | any authenticated |
| `/leads` | `leads/page.tsx` | `lead_read` |
| `/leads/[id]` | `leads/[id]/page.tsx` | `lead_read` |
| `/pipeline` | `pipeline/page.tsx` | `lead_read` (manage UI admin-gated) |
| `/tasks` | `tasks/page.tsx` | `task_read` |
| `/search` | `search/page.tsx` | `search` |
| `/ai` | `ai/page.tsx` | `lead_read` |
| `/ai/settings` | `ai/settings/page.tsx` | `ai_manage` (UI + API) |
| `/team` | `team/page.tsx` | `invite_manage` |
| `/assignment` | `assignment/page.tsx` | `lead_assign` |
| `/audit` | `audit/page.tsx` | `audit_read` |
| `/login` | `(auth)/login/page.tsx` | public |

## Permission Coverage (UI Mirror)

`frontend/src/lib/permissions.ts` mirrors the backend matrix. Page-level `can()`
gates verified in:

- `team/page.tsx` → `invite_manage`
- `assignment/page.tsx` → `lead_assign`
- `audit/page.tsx` → `audit_read`
- `pipeline/page.tsx` → `pipeline_manage` (stage editing)
- `leads/page.tsx` + `leads/[id]/page.tsx` → `lead_write` / `lead_delete` / `lead_assign`
- `tasks/page.tsx` → `task_write`
- `ai/settings/page.tsx` → `ai_manage` (**added during this audit**)

Nav links in `components/layouts/site-nav.tsx` are filtered by role; the
backend remains the enforcement source of truth.

## Changes Made During This Audit

1. **AI endpoint RBAC (backend + frontend).** The AI endpoints previously
   required only an authenticated session — any user, including `viewer`, could
   change org-wide LLM settings and trigger real n8n dispatch. Added:
   - `Permission.AI_MANAGE = "ai_manage"` in `backend/app/core/permissions.py`
     (MANAGE-level: owner/admin/manager), mirrored in `frontend/src/lib/permissions.ts`
   - `PATCH /api/v1/ai/settings` → requires `ai_manage`
   - `POST /api/v1/ai/run` and `POST /api/v1/ai/dispatch` → require `lead_write`
   - `GET /api/v1/ai/settings` and `/api/v1/ai/tools` remain authenticated-only (read)
   - `ai/settings/page.tsx` now renders a permission-denied message for
     non-managers instead of the form
   - Unit tests: `backend/tests/unit/test_permissions.py` (7 tests) +
     `frontend/src/lib/__tests__/permissions.test.ts` extended

## Session Handling

`frontend/src/lib/session.ts`:

- Stores the JWT pair + user profile in `localStorage` (key `agencyos.session`).
- Sets a short-lived marker cookie `agencyos.auth` (`samesite=lax`) for
  route-level redirects — the cookie never carries the token.
- Corrupt localStorage is detected and cleared; session reads are cached.

**Residual risk (documented, not a blocker):** the access token lives in
`localStorage`, making it readable by any XSS-injected script. This is the
standard trade-off for a token-based SPA and matches the backend's stateless
JWT design; mitigation is the backend's CSP + `nosniff`/`X-Frame-Options`
headers and the fact that refresh tokens are rotated and revocable.

## Env Validation

`frontend/src/lib/env.ts` validates `NEXT_PUBLIC_API_URL` and
`NEXT_PUBLIC_APP_ENV` with zod and fails fast at startup on invalid config —
no silent misbehavior in production.

## Security Headers

`frontend/next.config.mjs` applies `X-Content-Type-Options: nosniff`,
`X-Frame-Options: SAMEORIGIN`, `Referrer-Policy: strict-origin-when-cross-origin`,
`Permissions-Policy` (no camera/mic/geolocation) on all routes, mirroring the
backend's middleware.

## Gaps and Recommendations

1. **Invite accept page missing (GAP).** `TeamService.invite_url()` generates
   `{FRONTEND_URL}/invite/{raw_token}`, and the team page shows that link, but
   no `/invite/[token]` route exists — the link is currently a dead end. The
   backend lookup/accept endpoints are complete and tested; the frontend page
   is a Phase 5 UI item. **Deferred to Phase 5 by decision.**
2. **`postcss.config.mjs` lint warning.** Cosmetic; no functional impact.
3. **XSS residual risk** on token-in-localStorage (documented above).

## Conclusion

**Status: ✅ PASS (ready with documented deferrals).** All four frontend gates
pass (lint/typecheck/format/68 tests). Route and permission coverage is
complete for every shipped surface. One UI gap (invite-accept page) is
explicitly deferred to Phase 5 with backend endpoints already in place.
