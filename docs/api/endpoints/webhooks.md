# Webhooks

Inbound, secret-authenticated endpoints for external systems (n8n workflows,
contact forms) to push data into AgencyOS. Unlike the rest of the API they do
**not** require a user session.

## Authentication

Every webhook request must send the shared secret in the `X-AgencyOS-Webhook`
header:

```
X-AgencyOS-Webhook: <WEBHOOK_SECRET>
```

`WEBHOOK_SECRET` is set via environment configuration (`backend/.env.example`
templates it; `app/core/config.py` reads it). When the value is empty the
endpoints refuse to operate with `503 webhook.not_configured` — webhooks are
opt-in per deployment.

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
| `401`  | error envelope                        | Missing/incorrect `X-AgencyOS-Webhook` |
| `404`  | error envelope                        | Unknown `organization_slug`           |
| `503`  | error envelope                        | `WEBHOOK_SECRET` not configured       |

Duplicate detection uses the same normalizers as the lead API
(`email_normalized`, `phone_normalized`, `website_domain`).

### Error codes

- `webhook.not_configured` — secret unset, webhooks disabled
- `webhook.invalid_secret` — bad or missing `X-AgencyOS-Webhook`
- `webhook.missing_org` — `organization_slug` not supplied
- `webhook.unknown_org` — slug does not resolve to an organization

Errors use the standard envelope: `{"error": {"code", "message", "details"?}}`.

## Example: curl

```bash
curl -s -X POST "https://api.example.com/api/v1/webhooks/leads" \
  -H "Content-Type: application/json" \
  -H "X-AgencyOS-Webhook: $WEBHOOK_SECRET" \
  -d '{"organization_slug": "acme", "email": "ada@example.com", "first_name": "Ada"}'
```
