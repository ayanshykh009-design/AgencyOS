# Webhooks

Inbound, secret-authenticated endpoints for external systems (n8n workflows,
contact forms) to push data into AgencyOS. Unlike the rest of the API they do
**not** require a user session.

## Authentication

Every webhook request must send the shared secret in the `X-AgencyOS-Webhook`
header and, when a shared secret is configured, must also be signed with that
same secret:

```
X-AgencyOS-Webhook: <WEBHOOK_SECRET>
X-AgencyOS-Timestamp: <unix-seconds>
X-AgencyOS-Nonce: <url-safe-nonce>
X-AgencyOS-Signature: <hex-hmac-sha256>
```

`WEBHOOK_SECRET` is set via environment configuration (`backend/.env.example`
templates it; `app/core/config.py` reads it). When the value is empty the
endpoint refuses to operate with `503 webhook.not_configured` — webhooks are
opt-in per deployment.

The signature is:

```
hex(HMAC_SHA256(WEBHOOK_SECRET, "<timestamp>.<nonce>." + exact_raw_request_body))
```

Rules:

- `X-AgencyOS-Timestamp` is a Unix timestamp in seconds. Its absolute skew from
  server time must be within `WEBHOOK_TIMESTAMP_SKEW_SECONDS` (default 300).
- `X-AgencyOS-Nonce` is 8–128 characters from `A-Za-z0-9_-` and is single-use
  for `WEBHOOK_REPLAY_TTL_SECONDS` (default 600), scoped to the organization
  slug.
- `X-AgencyOS-Signature` is a 64-character hex HMAC-SHA256 digest, compared in
  constant time.
- The signed bytes are the exact body sent over the wire. Do not reformat or
  re-serialize JSON after computing the signature.

Deployed environments use shared Redis for replay protection and fail closed
with `503 webhook.replay_unavailable` if the store cannot be reached. Explicit
local environments use a bounded process-local replay cache. If lead ingestion
fails after a nonce is reserved, the reservation is released with a claim token
so a legitimate retry can complete.

Keep the secret out of code and out of version control; supply it to n8n as an
encrypted credential (n8n HTTP Request node → credential → header).

## POST /api/v1/webhooks/leads

Ingest a single lead from an external system. The organization is resolved from
`organization_slug` instead of a session, so no user context is needed.

### Request body

All `LeadCreate` fields apply, minus `organization_id` (always derived from the
slug). The webhook adds:

| Field                | Type      | Required | Notes                              |
| -------------------- | --------- | -------- | ---------------------------------- |
| `organization_slug`  | string    | yes      | Slug of the org to attribute the lead to |
| `lead_source_id`     | UUID      | no       | Lead source attribution            |
| `owner_user_id`      | UUID      | no       | Assign the lead to a user          |

Standard lead fields (`first_name`, `last_name`, `email`, `phone`, `website`,
`status`, `score`, …) match the lead schema; at least one contact channel
(email/phone/whatsapp/website) is required.

```json
{
  "organization_slug": "acme",
  "first_name": "Ada",
  "last_name": "Lovelace",
  "company": "Analytical Engines",
  "position": "Founder",
  "email": "ada@example.com",
  "website": "https://example.com"
}
```

### Responses

| Status | Body                                  | Meaning                               |
| ------ | ------------------------------------- | ------------------------------------- |
| `201`  | `{"lead_id": "<uuid>", "duplicate": false}` | Lead created                    |
| `201`  | `{"lead_id": "<uuid>", "duplicate": true}`  | Duplicate matched, existing lead returned idempotently |
| `400`  | error envelope                        | Missing `organization_slug` or invalid lead body |
| `401`  | error envelope                        | Missing/incorrect secret, or missing/stale/malformed/invalid signature |
| `404`  | error envelope                        | Unknown `organization_slug`           |
| `409`  | error envelope                        | Duplicate `X-AgencyOS-Nonce` (`webhook.replay_detected`) |
| `503`  | error envelope                        | Secret not configured, or deployed replay guard unavailable |

Duplicate detection uses the same normalizers as the lead API
(`email_normalized`, `phone_normalized`, `website_domain`).

### Error codes

- `webhook.not_configured` — shared secret unset, webhooks disabled (`503`)
- `webhook.invalid_secret` — bad or missing `X-AgencyOS-Webhook` (`401`)
- `webhook.invalid_signature` — missing/stale/malformed/wrong signed headers or signature (`401`)
- `webhook.missing_org` — `organization_slug` not supplied (`400`)
- `webhook.unknown_org` — slug does not resolve to an organization (`404`)
- `webhook.replay_detected` — nonce already used for this organization (`409`)
- `webhook.replay_unavailable` — deployed replay guard could not reserve the nonce (`503`)

Errors use the standard envelope: `{"error": {"code", "message", "details"?}}`.
No secret, signature, or raw payload is included in error details.

## Example: curl

```bash
BODY='{"organization_slug":"acme","email":"ada@example.com","first_name":"Ada"}'
TS="$(date +%s)"
NONCE="$(openssl rand -hex 16)"
SIGNED="${TS}.${NONCE}.${BODY}"
SIG="$(printf '%s' "$SIGNED" | openssl dgst -sha256 -hmac "$WEBHOOK_SECRET" -hex | awk '{print $2}')"

curl -s -X POST "https://api.example.com/api/v1/webhooks/leads" \
  -H "Content-Type: application/json" \
  -H "X-AgencyOS-Webhook: $WEBHOOK_SECRET" \
  -H "X-AgencyOS-Timestamp: $TS" \
  -H "X-AgencyOS-Nonce: $NONCE" \
  -H "X-AgencyOS-Signature: $SIG" \
  -d "$BODY"
```

The `-d` body must be byte-for-byte identical to the value used in `SIGNED`.
