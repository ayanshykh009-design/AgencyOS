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
| `400` `workflow.builtin_definition_invalid` | `execution_mode=builtin` but `definition` is malformed (see below) |
| `409` `workflow.name_conflict` | A workflow with this name already exists in the org |
| `422` (Pydantic) | Blank `name` or invalid `execution_mode` |

## Builtin execution definitions

When `execution_mode` is `builtin`, the workflow runs **in-process** via the
builtin step engine (`app/services/builtin_execution.py`) — no n8n instance is
needed. `definition` is validated on create/update (400 above) and is a JSON
object with two optional keys:

- `steps` — an ordered list of steps sharing a `context` that starts as
  `{"input": <execution input>}`. An empty or absent list is valid and returns
  the input context unchanged.
- `output_key` — context key whose value becomes the execution output; when
  omitted the whole context is returned.

### Step types

| Step | Fields | Behavior |
| ---- | ------ | -------- |
| `set` | `key`, `value` | Writes `value` into `context[key]`. If `value` is a string containing `{{ ... }}` it is rendered as a template, otherwise it is copied literally. |
| `copy` | `from`, `to` | Deep-copies the value at dotted path `from` into `context[to]`. Missing source fails the run. |
| `condition` | `if`, `then`, `else?` | Runs `then`/`else` (each a list of steps) based on the guard. |
| `error_if` | `message`, `if` | Fails the execution with `message` when the guard is true (business validation). |

`condition.then`/`else` may nest other steps, including further conditions.

### Guard `if`

`{"path": "…", "op": "…", "value": …}` where `path` is a dotted path into the
context. Operators:

| Op | Value | Meaning |
| -- | ----- | ------- |
| `eq` / `ne` | any | equality / inequality |
| `gt` / `gte` / `lt` / `lte` | scalar | comparison (must be comparable) |
| `in` / `not_in` | list | resolved value is in the list; for list values, whether any element overlaps |
| `contains` | string | resolved string/list contains the value |
| `exists` / `missing` | — | whether the path resolves |

A missing path makes comparison/collection guards evaluate false
(`exists`/`missing` still work).

### Templates

`{{ path }}` resolves `path` against the context; `{{ path ?? default }}`
substitutes `default` when the path is missing. Paths and step keys may only
use `[A-Za-z0-9_]` — there is no expression evaluation (no eval/exec), so a
misconfigured workflow cannot run arbitrary code.

### Limits (config)

| Setting | Default | Meaning |
| ------- | ------- | ------- |
| `BUILTIN_MAX_STEPS` | 50 | Total steps executed (incl. branches) |
| `BUILTIN_MAX_CONDITION_DEPTH` | 3 | Max condition nesting depth |
| `BUILTIN_MAX_TEMPLATE_LENGTH` | 4000 | Max characters in one template |
| `BUILTIN_MAX_RESULT_SIZE_BYTES` | 524288 | Max serialized result payload |

### Example

```json
{
  "steps": [
    {"type": "copy", "from": "input.lead", "to": "lead"},
    {"type": "set", "key": "greeting", "value": "Hello {{ lead.first_name }}"},
    {"type": "condition",
     "if": {"path": "lead.score", "op": "gte", "value": 50},
     "then": [{"type": "set", "key": "segment", "value": "hot"}],
     "else": [{"type": "set", "key": "segment", "value": "cold"}]},
    {"type": "error_if", "message": "lead.email is required",
     "if": {"path": "lead.email", "op": "missing"}}
  ],
  "output_key": "lead"
}
```

Builtin executions reuse the standard execution lifecycle (queue → running →
succeeded/failed), including retries and timeouts. A failing step surfaces as
`error: "adapter_error"` with the step's message.

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

## GET /api/v1/workflows/{workflow_id}/executions

List executions scoped to one workflow (shortcut over
`/workflow-executions`). Paginated with `limit` (1–200, default 50) and
`offset`; `status` filters to a single execution state; `sort` is
`created_at` (default), `started_at`, `finished_at`, or `status`; `order` is
`asc` or `desc` (default `desc`). Returns a `Page` envelope.

## Authentication

`Authorization: Bearer <token>`. Errors use the standard envelope.
