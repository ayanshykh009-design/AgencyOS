# Credentials

Org-scoped secrets (API keys) used by the n8n / built-in integration layer. All
endpoints are JWT-authenticated and require `credential_manage` (OWNER/ADMIN
only — reads, writes, and deletion all use the same capability today).

Security invariants:

- Values are encrypted **at rest** with versioned envelope encryption
  (`app/core/crypto.py`): a row stores `v<key_version>:<base64(nonce || ct)>`.
  The plaintext is **never** returned by any endpoint — responses expose only
  `value_preview`.
- `encrypted_value` and `value_preview` are **not updatable** after creation —
  rotate (see below) instead of delete + recreate.
- Each credential carries a `key_version` and `last_rotated_at` so you can audit
  which master key encrypted it and when it was last re-encrypted.

## POST /api/v1/credentials

Create a credential. Returns 201. The value is encrypted with the current key
on write.

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

Each item includes `key_version` and `last_rotated_at`.

## GET /api/v1/credentials/{credential_id}

Fetch one credential. The response never includes `encrypted_value`.

## PATCH /api/v1/credentials/{credential_id}

Partial update of metadata only (`name`, `credential_type`, `description`,
`expires_at`). The secret is never replaced here — use rotation.

## POST /api/v1/credentials/{credential_id}/rotate

Re-encrypt the stored value with the current key version and stamp
`last_rotated_at`. Idempotent and backward compatible: pre-versioning rows
(stored before Phase 5B) are upgraded to encrypted-at-rest on first rotation.
Returns the updated `CredentialRead`.

## DELETE /api/v1/credentials/{credential_id}

Delete a credential. Returns 204.

## Key rotation (operational)

Rotating the master key is a two-phase, zero-downtime operation:

1. Set the **new** key in `CREDENTIALS_ENC_KEY`, move the old one to
   `CREDENTIALS_ENC_KEY_PREVIOUS`, and bump `CREDENTIAL_KEY_VERSION` (e.g. `1`
   → `2`). Old rows stay readable through the previous key (dual-read).
2. Enable the rekey worker (`CREDENTIAL_REKEY_ENABLED=true`,
   `python -m app.workers.credential_worker`). It re-encrypts rows in batches
   (`CREDENTIAL_REKEY_BATCH`) and retires the previous key version from the
   `credential_key_versions` registry once no stale rows remain.
3. Only after `credential_rekey_processed` has caught up and the stale count is
   zero may `CREDENTIALS_ENC_KEY_PREVIOUS` be cleared.

Rotate a single credential at any time via the rotate endpoint above.

## Authentication

`Authorization: Bearer <token>`. Errors use the standard envelope.
