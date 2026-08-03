# Audit Logs

Enriched, read-only access to the append-only activity trail. Requires
`audit_read` permission (admin only). Entries include actor metadata (the acting
user's id and name) resolved via an eager-loaded relationship.

## GET /api/v1/audit

List audit entries, newest first, with optional filters.

| Query param     | Type      | Notes                                   |
| --------------- | --------- | --------------------------------------- |
| `entity_type`   | string    | `lead`, `task`, `note`, `user`, …       |
| `entity_id`     | UUID      | Specific entity id                      |
| `lead_id`       | UUID      | Entries touching one lead               |
| `user_id`       | UUID      | Entries performed by one user           |
| `event_type`    | enum      | `lead_won`, `task_completed`, `note_created`, … |
| `occurred_after` / `occurred_before` | datetime | Time window            |
| `limit` / `offset` | int     | Pagination (limit 1–500, default 50)    |

## GET /api/v1/audit/entity/{entity_type}/{entity_id}

Trail for a single entity (e.g. everything that ever happened to one task or
note). Optional `event_type`, `limit`, `offset`.

## Response shape

Each entry:

```json
{
  "id": "…",
  "organization_id": "…",
  "user_id": "…",
  "lead_id": "…",
  "event_type": "task_completed",
  "entity_type": "task",
  "entity_id": "…",
  "description": "…",
  "metadata": {},
  "occurred_at": "2026-08-03T09:00:00Z",
  "created_at": "2026-08-03T09:00:00Z",
  "actor_user_id": "…",
  "actor_name": "Ada Lovelace"
}
```

`actor_user_id`/`actor_name` mirror the acting user (name falls back to email);
they are `null` for system-generated events. The trail is append-only — there
are no write endpoints under `/audit`.

## Authentication

`Authorization: Bearer <token>` and the `audit_read` role capability. Errors use
the standard envelope.
