# Memory

AI memory and durable knowledge items. The memory *retrieval/reasoning* logic
lands in M4 — these endpoints are pure CRUD over the `ai_memories` and
`knowledge_items` tables. All endpoints are JWT-authenticated. Reads require
`memory_read`; writes require `memory_write` (manager+).

## GET /api/v1/memory

List AI memories, optionally filtered by `memory_type` (`working` or
`long_term`) and `scope`.

| Query param   | Type   | Notes                  |
| ------------- | ------ | ---------------------- |
| `memory_type` | enum   | Optional               |
| `scope`       | enum   | Optional               |
| `limit`       | int    | 1–500, default 100     |
| `offset`      | int    | Default 0              |

## POST /api/v1/memory

Create a memory. Returns 201.

```json
{"scope": "conversation", "content": "Prefers annual pricing."}
```

## GET /api/v1/memory/{memory_id}

Fetch a single memory.

## PATCH /api/v1/memory/{memory_id}

Partial update of `scope`, `source_id`, `title`, `content`, `importance`,
`tags`, and `metadata`. `memory_type` is immutable after creation.

## DELETE /api/v1/memory/{memory_id}

Delete a memory. Returns 204.

## Knowledge items

Durable long-term knowledge, optionally promoted from a working memory
(`source_memory_id`).

## GET /api/v1/memory/knowledge

List knowledge items, optionally filtered by `category`.

## GET /api/v1/memory/knowledge/search

Substring search over title/content.

| Query param | Type   | Notes                  |
| ----------- | ------ | ---------------------- |
| `q`         | string | Required, min length 1 |
| `limit`     | int    | 1–200, default 50      |

## POST /api/v1/memory/knowledge

Create a knowledge item. Returns 201.

## GET /api/v1/memory/knowledge/{item_id}

Fetch a single knowledge item.

## PATCH /api/v1/memory/knowledge/{item_id}

Partial update of `source_memory_id`, `title`, `content`, `category`, `tags`,
and `metadata`.

## DELETE /api/v1/memory/knowledge/{item_id}

Delete a knowledge item. Returns 204.

## Authentication

`Authorization: Bearer <token>`. Errors use the standard envelope.
