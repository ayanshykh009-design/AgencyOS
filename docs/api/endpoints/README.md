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
- `workflows.md` — workflow CRUD + lifecycle transitions
- `workflow-triggers.md` — trigger definitions (manual / event / schedule)
- `workflow-executions.md` — execution queue, history, retries, timeline
- `workflow-events.md` — event publishing for event-driven triggers
- `automation-control.md` — global pause/resume kill switch (admin-only)
- `monitoring.md` — operator monitoring: workers, statistics, queue depth
- `credentials.md` — org-scoped secrets (envelope-encrypted) for integrations

Each file documents: request/response schemas, auth requirements, error codes,
and example payloads. Implement alongside the endpoints — docs rot fast if
written late.
