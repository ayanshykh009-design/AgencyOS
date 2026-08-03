# Endpoint Reference

One file per endpoint group, e.g.:

- `health.md` — liveness probes
- `auth.md` — register, login, refresh, me (pending implementation)
- `pipeline.md` — stages, close reasons, Kanban board, stage moves
- `tasks.md` — task CRUD, completion, recurrence, reminders
- `notes.md` — lead notes (body + pin)
- `dashboard.md` — aggregate analytics snapshot
- `search.md` — unified search across leads, tasks, notes
- `exports.md` — CSV/JSON lead export
- `audit.md` — admin-only audit trail with actor metadata
- `ai.md` — AI brain orchestrator
- `webhooks.md` — external ingestion (n8n / contact forms)

Each file documents: request/response schemas, auth requirements, error codes,
and example payloads. Implement alongside the endpoints — docs rot fast if
written late.
