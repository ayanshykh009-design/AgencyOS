# Outreach

Outreach message templates, per-lead send attempts, follow-up sequences, and the
manual outreach queue. All endpoints are JWT-authenticated and always scoped to
the caller's organization: ids belonging to another tenant return `404`.

## Authorization

| Endpoint                                          | Required permission         |
| ------------------------------------------------- | --------------------------- |
| `GET /api/v1/outreach/messages`                   | any authenticated           |
| `GET /api/v1/outreach/messages/{message_id}`      | any authenticated           |
| `POST /api/v1/outreach/messages`                  | admin only (`owner`/`admin`) |
| `PATCH /api/v1/outreach/messages/{message_id}`    | admin only (`owner`/`admin`) |
| `DELETE /api/v1/outreach/messages/{message_id}`   | admin only (`owner`/`admin`) |
| `GET /api/v1/outreach/leads/{lead_id}/attempts`   | any authenticated           |
| `GET /api/v1/outreach/leads/{lead_id}/follow-ups` | any authenticated           |
| `GET /api/v1/outreach/manual`                     | any authenticated           |
| `GET /api/v1/outreach/manual/{task_id}`           | any authenticated           |
| `POST /api/v1/outreach/attempts`                  | `lead_write`                |
| `PATCH /api/v1/outreach/attempts/{attempt_id}`    | `lead_write`                |
| `POST /api/v1/outreach/follow-ups`                | `lead_write`                |
| `PATCH /api/v1/outreach/follow-ups/{follow_up_id}`| `lead_write`                |
| `POST /api/v1/outreach/manual`                    | `lead_write`                |
| `PATCH /api/v1/outreach/manual/{task_id}`         | `lead_write`                |

Attempts, follow-ups, and manual tasks are lead-scoped CRM records (each create
requires a `lead_id`), so writes require `lead_write`. That permission is granted
to `owner`, `admin`, `manager`, `member`, and `sales_agent` — `viewer` is
read-only and receives `403` on every write route. Reads remain
authenticated-only, matching lead reads.

## Message templates

### GET /api/v1/outreach/messages

List templates, newest first.

| Query param | Type  | Notes                            |
| ----------- | ----- | -------------------------------- |
| `channel`   | enum  | Optional channel filter          |
| `limit`     | int   | 1–500, default 100               |
| `offset`    | int   | Default 0                        |

### POST /api/v1/outreach/messages

Create a template (`name`, `channel`, `body`; optional `subject`, `variables`,
`version`, `is_active`). Returns 201. Admin only.

### GET /api/v1/outreach/messages/{message_id}

Fetch one template.

### PATCH /api/v1/outreach/messages/{message_id}

Partial update of a template. Admin only.

### DELETE /api/v1/outreach/messages/{message_id}

Delete a template. Returns 204. Admin only.

## Attempts

### GET /api/v1/outreach/leads/{lead_id}/attempts

List every send attempt recorded for a lead.

### POST /api/v1/outreach/attempts

Record an attempt. Returns 201.

```json
{"organization_id": "…", "lead_id": "…", "channel": "email", "status": "queued"}
```

`organization_id` is always replaced with the caller's organization.

### PATCH /api/v1/outreach/attempts/{attempt_id}

Partial update of delivery tracking (`status`, `scheduled_at`, `sent_at`,
`delivered_at`, `external_id`, `error_code`, `error_message`, `metadata`).

## Follow-ups

### GET /api/v1/outreach/leads/{lead_id}/follow-ups

List a lead's follow-up sequence.

### POST /api/v1/outreach/follow-ups

Create a follow-up. Returns 201.

```json
{"organization_id": "…", "lead_id": "…", "channel": "email",
 "sequence_position": 1, "body": "Checking in"}
```

### PATCH /api/v1/outreach/follow-ups/{follow_up_id}

Partial update of `subject`, `body`, `delay_days`, `scheduled_at`, `status`,
`sent_at`.

## Manual queue

### GET /api/v1/outreach/manual

List manual outreach tasks.

| Query param        | Type | Notes                    |
| ------------------ | ---- | ------------------------ |
| `status`           | enum | Optional status filter   |
| `assigned_user_id` | UUID | Optional assignee filter |

### GET /api/v1/outreach/manual/{task_id}

Fetch one manual task.

### POST /api/v1/outreach/manual

Queue a manual task. Returns 201.

```json
{"organization_id": "…", "lead_id": "…", "channel": "email", "priority": 0}
```

### PATCH /api/v1/outreach/manual/{task_id}

Partial update of `status`, `priority`, `due_at`, `subject`, `body`, `notes`,
`assigned_user_id`, `completed_at`.

## Authentication

`Authorization: Bearer <token>`. Missing/invalid tokens receive `401`; callers
without the required permission receive `403` before any handler runs, so a
rejected request never creates or mutates a row. Errors use the standard
envelope: `{"error": {"code", "message", "details"?}}`.
