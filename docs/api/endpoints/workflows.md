# Workflows

Org-scoped automation workflow definitions with a draft → active → paused →
archived lifecycle. All endpoints are JWT-authenticated. Reads require
`automation_read`, writes `automation_write`, lifecycle transitions and deletion
`automation_manage` (per the RBAC matrix).

## GET /api/v1/workflows

List workflows. Paginated with `limit` (1–200, default 50) and `offset`.

| Query param | Type | Notes |
| ----------- | ---- | ----- |
| `status`    | enum | `draft`, `active`, `paused`, `archived` |

Returns a `Page` envelope: `{items, total, limit, offset}`.

## GET /api/v1/workflows/active

List all `active` workflows (no pagination). Used by the trigger engine to find
workflows eligible for event-driven dispatch.

## POST /api/v1/workflows

Create a workflow. Returns 201.

```json
{
  "organization_id": "…",
  "name": "Lead intake enrichment",
  "description": "Enrich and score new leads",
  "definition": {},
  "execution_mode": "n8n",
  "config": {}
}
```

`execution_mode` must be `n8n` or `builtin` (default `n8n`). New workflows start
in `draft`.

| Error | Meaning |
| ----- | ------- |
| `400` `workflow.organization_required` | Missing `organization_id` (server sets it; defensive) |
| `409` `workflow.name_conflict` | A workflow with this name already exists in the org |
| `422` (Pydantic) | Blank `name` or invalid `execution_mode` |

## GET /api/v1/workflows/{workflow_id}

Fetch one workflow.

## PATCH /api/v1/workflows/{workflow_id}

Partial update (any field optional). `status` can be set directly here, but the
dedicated transition endpoints below are preferred because they enforce valid
lifecycle moves.

## POST /api/v1/workflows/{workflow_id}/activate

Move `draft` or `paused` → `active`. Requires `automation_manage`. Emits a
`workflow_activated` activity entry.

## POST /api/v1/workflows/{workflow_id}/pause

Move `active` → `paused`. Requires `automation_manage`.

## POST /api/v1/workflows/{workflow_id}/archive

Move any non-archived workflow → `archived`. Requires `automation_manage`.

## DELETE /api/v1/workflows/{workflow_id}

Delete a workflow. Only allowed for `draft` or `archived` workflows (active
workflows must be archived first). Requires `automation_manage`. Returns 204.

## Authentication

`Authorization: Bearer <token>`. Errors use the standard envelope.
