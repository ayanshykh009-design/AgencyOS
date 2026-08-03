# Notes

Internal notes attached to a lead (body text + pin flag). All endpoints are
JWT-authenticated. Reads require `note_read`, writes `note_write`.

## GET /api/v1/notes

List notes for a lead. `lead_id` (UUID) is **required**.

| Query param | Type | Notes                                    |
| ----------- | ---- | ---------------------------------------- |
| `lead_id`   | UUID | Required — notes are scoped per lead     |
| `limit`     | int  | 1–200, default 100                       |
| `offset`    | int  | Default 0                                |

Results are pinned-first, then newest first. Returns a `Page` envelope.

## POST /api/v1/notes

Create a note. Returns 201.

```json
{"lead_id": "…", "body": "Prefers pricing on annual terms.", "pinned": false}
```

| Error                         | Meaning                    |
| ----------------------------- | -------------------------- |
| `400` `note.body_required`    | Blank body                 |
| `404` `lead.not_found`        | Lead not in caller's org   |

Emits a `note_created` activity entry.

## GET /api/v1/notes/{note_id}

Fetch one note.

## PATCH /api/v1/notes/{note_id}

Partial update of `body` and/or `pinned`. Emits `note_updated`.

## DELETE /api/v1/notes/{note_id}

Delete a note. Returns 204. Emits `note_deleted`.

## Authentication

`Authorization: Bearer <token>`. Errors use the standard envelope.
