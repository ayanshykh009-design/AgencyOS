# Conversations

Record-only reply threads attached to a lead on a single channel (email, WhatsApp,
contact form, LinkedIn, Instagram, Facebook). Conversations live **only inside
Lead Detail** — there is no separate inbox/messaging surface in V1.

**Record-only delivery:** `add_message` records an AGENT message in AgencyOS. It
does **not** dispatch email, WhatsApp, or any other external provider message.
Nothing in this API sends anything externally. The backend stamps sender identity
and timestamps server-side; the client never chooses a tenant or sender identity.

All endpoints are JWT-authenticated. Reads require `lead_read`; writes
(`POST`/`PATCH`/message creation) require `lead_write`.

## GET /api/v1/conversations/open

List open conversations for the authenticated organization, newest first
(`last_message_at` descending, nulls last). Paginated with `limit` (1–200,
default 50) and `offset` (default 0).

| Query param | Type | Notes |
| ----------- | ---- | ----- |
| `limit`     | int  | 1–200, default 50 |
| `offset`    | int  | Default 0 |

Returns `list[ConversationRead]`.

## GET /api/v1/conversations/leads/{lead_id}

List every conversation thread for one lead (open and closed), newest first
(`updated_at` descending). Tenant-scoped: a lead belonging to another
organization yields 404.

Path param: `lead_id` (UUID).

Returns `list[ConversationRead]`.

| Error | Meaning |
| ----- | ------- |
| `404` `conversation.lead_not_found` | Lead does not exist in this organization |

## POST /api/v1/conversations

Create a new conversation thread for a lead. Returns 201.

```json
{
  "organization_id": "…",
  "lead_id": "…",
  "channel": "email",
  "subject": "Re: proposal",
  "is_open": true,
  "external_thread_id": "provider-thread-id"
}
```

| Field                | Type   | Notes |
| -------------------- | ------ | ----- |
| `organization_id`    | UUID   | Required; must match the authenticated principal's organization |
| `lead_id`            | UUID   | Required; lead must exist in this organization |
| `channel`            | enum   | `email`, `whatsapp`, `contact_form`, `linkedin`, `instagram`, `facebook` |
| `subject`            | string | Optional, max 255 (DB `text`) |
| `is_open`            | bool   | Default `true` |
| `external_thread_id` | string | Optional provider thread id |

**Uniqueness (backend-enforced):** at most one **open** conversation per
`(lead, channel)` (partial unique index `uq_conversations_open_per_channel`,
`WHERE is_open`). A second open thread on the same lead/channel returns
`409 conversation.duplicate_open` with the message
`"An open conversation already exists for this lead and channel"`. Closing the
existing thread (or choosing another channel) allows a new one.

| Error | Meaning |
| ----- | ------- |
| `404` `conversation.lead_not_found` | Lead does not exist in this organization |
| `409` `conversation.duplicate_open` | An open conversation already exists for this lead and channel |

Returns `ConversationRead`.

## GET /api/v1/conversations/{conversation_id}

Fetch one conversation thread. Tenant-scoped.

Path param: `conversation_id` (UUID).

Returns `ConversationRead`.

| Error | Meaning |
| ----- | ------- |
| `404` `conversation.not_found` | Conversation does not exist in this organization |

## PATCH /api/v1/conversations/{conversation_id}

Partial update of a conversation thread. All fields optional. Returns the
updated thread with a refreshed `updated_at`. Requires `lead_write`.

```json
{
  "subject": "Re: revised proposal",
  "is_open": false,
  "last_message_at": "2026-08-05T09:00:00Z"
}
```

| Field             | Type      | Notes |
| ----------------- | --------- | ----- |
| `subject`         | string\|null | |
| `is_open`         | bool\|null | `true` = Open, `false` = Closed |
| `last_message_at` | datetime\|null | |

Returns `ConversationRead`.

| Error | Meaning |
| ----- | ------- |
| `404` `conversation.not_found` | Conversation does not exist in this organization |

## GET /api/v1/conversations/{conversation_id}/messages

List messages in a thread, oldest first. Paginated with `limit` (1–1000,
default 200) and `offset` (default 0). Tenant-scoped.

Path param: `conversation_id` (UUID).

| Query param | Type | Notes |
| ----------- | ---- | ----- |
| `limit`     | int  | 1–1000, default 200 |
| `offset`    | int  | Default 0 |

Returns `list[ConversationMessageRead]`.

| Error | Meaning |
| ----- | ------- |
| `404` `conversation.not_found` | Conversation does not exist in this organization |

## POST /api/v1/conversations/{conversation_id}/messages

Record a message in a thread. Returns 201. The authenticated caller is always
the server-authoritative sender for `AGENT` messages; `sender_user_id` and
timestamps are stamped server-side and cannot be overridden by the client. Only
`AGENT` sender type is accepted on this path; `LEAD` messages arrive via the
trusted inbound ingress path (not exposed as an HTTP endpoint).

```json
{
  "conversation_id": "…",
  "organization_id": "…",
  "sender_type": "agent",
  "body": "Following up on the proposal",
  "external_id": "provider-message-id",
  "metadata": {}
}
```

| Field             | Type   | Notes |
| ----------------- | ------ | ----- |
| `conversation_id` | UUID   | Required; must match the path |
| `organization_id` | UUID   | Required; must match the authenticated principal's organization |
| `sender_type`     | enum   | Must be `agent` on this path |
| `body`            | string | Required, min length 1 |
| `external_id`     | string | Optional provider message id |
| `metadata`        | object | Optional, default `{}` |
| `sent_at`         | datetime | Optional; server stamps when omitted |

Returns `ConversationMessageRead`.

| Error | Meaning |
| ----- | ------- |
| `403` `conversation.sender_not_allowed` | `sender_type` is not `agent` |
| `404` `conversation.not_found` | Conversation does not exist in this organization |
| `422` `conversation.invalid_sender` | Unknown `sender_type` |
| `422` `conversation.actor_required` | No authenticated actor (should not occur via HTTP) |

**Record-only:** this endpoint records the message in AgencyOS. It does **not**
send anything through email, WhatsApp, or any external channel.

## Schemas

### ConversationRead

```json
{
  "id": "uuid",
  "organization_id": "uuid",
  "lead_id": "uuid",
  "channel": "email",
  "external_thread_id": "string | null",
  "subject": "string | null",
  "is_open": true,
  "last_message_at": "datetime | null",
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

### ConversationMessageRead

```json
{
  "id": "uuid",
  "conversation_id": "uuid",
  "organization_id": "uuid",
  "sender_type": "agent | lead | system",
  "sender_user_id": "uuid | null",
  "body": "string",
  "external_id": "string | null",
  "metadata": {},
  "sent_at": "datetime | null",
  "created_at": "datetime"
}
```

## Authentication

`Authorization: Bearer <token>`. Errors use the standard envelope
`{error: {code, message, details}}`. All reads require `lead_read`; all writes
require `lead_write`.
