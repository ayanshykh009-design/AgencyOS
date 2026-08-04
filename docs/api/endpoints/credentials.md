# Credentials

Org-scoped secrets (API keys) used by the n8n integration layer. All endpoints
are JWT-authenticated. Reads require `credential_read`, writes
`credential_write`, deletion `credential_delete` (admin-only).

Security invariants:

- `encrypted_value` is stored encrypted at rest and is **never** returned by any
  endpoint. Responses expose only `value_preview`.
- `encrypted_value` and `value_preview` are **not updatable** after creation —
  rotate by delete + recreate.

## POST /api/v1/credentials

Create a credential. Returns 201.

```json
{
  "organization_id": "…",
  "name": "n8n production",
  "credential_type": "n8n_api_key",
  "encrypted_value": "secret-value",
  "value_preview": "abcd…wxyz",
  "description": "Prod n8n",
  "expires_at": null
}
```

`credential_type` is `n8n_api_key`, `api_key`, or `basic_auth`.

## GET /api/v1/credentials

List credentials. Paginated with `limit` (1–200, default 50) and `offset`.

| Query param       | Type | Notes                         |
| ----------------- | ---- | ----------------------------- |
| `credential_type` | enum | Filter by credential type     |

## GET /api/v1/credentials/{credential_id}

Fetch one credential. The response never includes `encrypted_value`.

## PATCH /api/v1/credentials/{credential_id}

Partial update of metadata only (`name`, `credential_type`, `description`,
`expires_at`). Changing the secret requires delete + recreate.

## DELETE /api/v1/credentials/{credential_id}

Delete a credential. Requires `credential_delete` (OWNER/ADMIN). Returns 204.

## Authentication

`Authorization: Bearer <token>`. Errors use the standard envelope.
