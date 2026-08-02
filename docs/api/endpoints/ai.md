# AI Automation

AI endpoints power the M11/M12/M13 "AI brain" surface: an orchestrator that
plans a goal (research a lead, draft outreach, dispatch via n8n), selects tools,
and executes them through the LLM provider layer. All endpoints are session
authenticated (JWT) and organization-scoped — a user only ever touches their own
org's leads and settings.

## POST /api/v1/ai/run

Run the AI brain for a single goal against one lead.

### Request body

| Field             | Type                    | Required | Notes                                     |
| ----------------- | ----------------------- | -------- | ----------------------------------------- |
| `goal`            | string (1–100)          | yes      | `research_lead`, `draft_email`, `draft_linkedin`, `search_leads`, `dispatch_outreach` |
| `lead_id`         | UUID                    | yes      | Lead to operate on                        |
| `channel`         | `email` \| `linkedin`   | no       | Outreach channel (draft goals)            |
| `recent_messages` | array of objects        | no       | In-thread history to personalize against  |

```json
{
  "goal": "draft_email",
  "lead_id": "00000000-0000-0000-0000-000000000002",
  "channel": "email",
  "recent_messages": []
}
```

### Responses

| Status | Meaning                                                                 |
| ------ | ----------------------------------------------------------------------- |
| `200`  | Brain finished; inspect `success` to distinguish a clean answer from a failure |
| `404`  | Lead not found in the caller's org                                      |
| `502`  | LLM provider or n8n dispatch failed                                     |

Response body mirrors the brain result:

```json
{
  "success": true,
  "response": "Hi Ada, …",
  "error": null,
  "steps_taken": 2,
  "tool_calls": [
    {"name": "lead_research", "arguments": {"lead_id": "…"}},
    {"name": "draft_outreach", "arguments": {"lead_id": "…", "channel": "email"}}
  ],
  "tool_results": [
    {"ok": true, "error": null, "text": "…"}
  ]
}
```

### Error codes

- `lead.not_found` — the lead is not in the caller's org (404)
- `ai.invalid_provider` — per-org setting names an unsupported provider (400)
- `ai.dispatch_failed` — n8n rejected the dispatch (502)

## POST /api/v1/ai/dispatch

Hand a ready-to-send draft to the n8n automation platform (which performs the
actual SMTP / LinkedIn / WhatsApp send).

### Request body

| Field      | Type            | Required | Notes                                     |
| ---------- | --------------- | -------- | ----------------------------------------- |
| `workflow` | string (1–100)  | yes      | n8n workflow key, e.g. `outreach-dispatch` |
| `payload`  | object          | yes      | JSON the workflow accepts (draft, lead id) |

```json
{
  "workflow": "outreach-dispatch",
  "payload": {"lead_id": "00000000-0000-0000-0000-000000000002", "subject": "…", "body": "…"}
}
```

### Responses

| Status | Meaning                                     |
| ------ | ------------------------------------------- |
| `200`  | `{"workflow": "…", "status": 200, "data": {…}}` |
| `502`  | n8n unreachable or rejected the payload     |

### Error codes

- `ai.invalid_workflow` — blank workflow (400)
- `ai.dispatch_failed` — n8n call failed (502)

## GET /api/v1/ai/tools

Return the static tool manifest (names, descriptions, parameter schemas) without
making any LLM call. Powers capability discovery for the UI and MCP-style export.

### Responses

| Status | Meaning                        |
| ------ | ------------------------------ |
| `200`  | `[{ "name", "description", "parameters" }, …]` |

## GET /api/v1/ai/settings

Return the organization's *effective* AI configuration: the per-org override if
one is stored under `organizations.settings.ai`, otherwise the global env
defaults (`LLM_PROVIDER` / `LLM_DEFAULT_MODEL`).

```json
{"provider": "openai", "model": "gpt-4o-mini", "overridden": false}
```

| Field       | Type    | Notes                                            |
| ----------- | ------- | ------------------------------------------------ |
| `provider`  | string  | Effective provider                               |
| `model`     | string  | Effective default model                          |
| `overridden`| boolean | True when a per-org override is stored           |

## PATCH /api/v1/ai/settings

Store per-org AI defaults. Only fields supplied are updated; an empty patch is a
no-op. The provider is normalized to lowercase and validated against the
supported set (`openai`, `anthropic`, `gemini`, `openai-compatible`, `ollama`,
`deepseek`).

```json
{"provider": "anthropic", "model": "claude-3-5-sonnet"}
```

### Responses

| Status | Meaning                                       |
| ------ | --------------------------------------------- |
| `200`  | Resolved settings after the update            |
| `400`  | `ai.invalid_provider` for an unknown provider |

## Authentication

All endpoints require a bearer JWT (`Authorization: Bearer <token>`); missing or
invalid tokens receive `401 auth.missing_token` / `auth.invalid_token`. Scope is
always the authenticated user's organization.

Errors use the standard envelope: `{"error": {"code", "message", "details"?}}`.
