# AgencyOS — Owner Internal Test Runbook

## Purpose

Guide the owner through validating the existing product with ordinary internal use and capturing reproducible failures. Distinct from agent-executed synthetic tests.

## Setup (one-time)

1. Copy `backend/.env.example` → `backend/.env`; set `APP_ENV=development`, `APP_DEBUG=true`, a real `SECRET_KEY`, and `DATABASE_URL` pointing at a local Postgres.
2. Run `make up` (Postgres + Redis), then `make migrate-sql`.
3. Copy `frontend/.env.example` → `frontend/.env.local`; set `NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1`.
4. Start backend (`make backend`) and frontend (`make frontend`).

## Safe validation flow (use synthetic data only)

1. Register a new organization via the UI (creates an OWNER account).
2. Invite a VIEWER and a MEMBER (Settings → Team) using test email addresses you control.
3. Create 3–5 synthetic leads (use obviously fake names/emails, e.g. `test-lead-1@example.com`).
4. Exercise each surface:
   - Dashboard loads without console errors.
   - Leads: create, edit, delete (soft), search, filter by status.
   - Outreach: create message template (admin), create attempt/follow-up/manual task, verify VIEWER cannot write (expect 403).
   - Notes, tasks: create/edit/complete/delete.
   - Search: find a lead by name and by email.
   - Notifications: trigger by creating a task; mark read.
   - Reports: open growth/analytics pages; confirm no 500s.
5. Log out; confirm redirect to login; confirm protected routes redirect.

## Capturing failures

- Browser: DevTools → Console + Network tab; screenshot the failing request (status, URL, response body).
- Backend: copy the relevant log line from `storage/logs/backend.log` (if `LOG_TO_FILE=true`) or the uvicorn terminal, including the request ID header.
- Record: page URL, user role, action, expected vs actual, timestamp, request ID.

## What requires owner-only credentials

- Real SMTP delivery: provision `SMTP_*` and set `EMAIL_VERIFICATION_ENABLED=true` / `PASSWORD_RESET_ENABLED=true`, then test resend with an address you control.
- n8n: set `N8N_BASE_URL` + `WEBHOOK_SECRET`, then trigger a known workflow and confirm execution.
- AI providers: set a provider key + positive budgets, then run a low-cost AI action (e.g. `/ai/run` with a tiny goal) and confirm cost tracking.
- None of these were executed during this audit.

## Agent vs owner

- Agent tests: synthetic data, disposable DB, mocked externals, automated assertions.
- Owner tests: real browser, real (test) accounts, optional real providers, UX validation.
- Both are needed for a complete readiness picture; the agent audit does not replace owner UX validation.
