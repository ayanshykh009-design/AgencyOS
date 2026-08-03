# Exports

Read-only lead export as CSV or JSON. Requires `export` permission (manager+).
Exports respect the same filters as the lead list and are capped at 5,000 rows.

## GET /api/v1/exports/leads

| Query param     | Type    | Notes                                    |
| --------------- | ------- | ---------------------------------------- |
| `fmt`           | string  | `csv` (default) or `json`                |
| `query`         | string  | Substring across name/company/email/…    |
| `status`        | enum    | `new`, `researching`, `contacted`, …     |
| `source_id`     | UUID    | Lead source filter                       |
| `owner_user_id` | UUID    | Owner filter                             |
| `min_score` / `max_score` | int | Score range (0–100)            |

Returns the file as an attachment (`Content-Disposition: attachment;
filename="leads.csv"`). CSV columns: `id`, `status`, `score`, contact fields,
`deal_value`, stage/close-reason ids, win/loss timestamps, source/owner ids,
`created_at`, `updated_at`.

```json
{
  "count": 2,
  "leads": [
    {"id": "…", "status": "new", "score": 42, "email": "a@example.com", "…": "…"}
  ]
}
```

| Status | Meaning                              |
| ------ | ------------------------------------ |
| `200`  | Attachment body in the chosen format |
| `403`  | `export` permission required         |

## Authentication

`Authorization: Bearer <token>`. Errors use the standard envelope.
