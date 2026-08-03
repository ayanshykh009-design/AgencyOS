# Advanced Search

Unified, org-scoped text search across leads, tasks, and notes. Requires
`search` permission (any authenticated member).

## GET /api/v1/search

| Query param | Type   | Notes                                  |
| ----------- | ------ | -------------------------------------- |
| `q`         | string | 1–255 chars; substring match           |
| `limit`     | int    | Per-type result cap, 1–50, default 10  |

The query is matched case-insensitively against:

- **Leads** — first name, last name, company, email, position
- **Tasks** — title, description
- **Notes** — body

```json
{
  "query": "acme",
  "leads": [/* LeadRead[] */],
  "tasks": [/* TaskRead[] */],
  "notes": [/* NoteRead[] */],
  "counts": {"leads": 1, "tasks": 2, "notes": 0, "total": 3}
}
```

Results are newest-first within each type; an empty `q` returns empty sections
(200) rather than a validation error.

## Authentication

`Authorization: Bearer <token>`. Errors use the standard envelope.
