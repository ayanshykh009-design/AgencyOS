# Memory

AI memory and durable knowledge items. The CRUD endpoints below expose the data
plane over the `ai_memories` and `knowledge_items` tables. The M4 *retrieval /
reasoning* flows are **service-internal** (no new endpoints): captured memories
are ranked and folded into the AI system prompt as a bounded context block, and
working memories can be promoted into durable knowledge items from inside the
service. All endpoints are JWT-authenticated. Reads require `memory_read`;
writes require `memory_write` (manager+).

## Canonical memory types

M4 derives eight canonical types from the row fields — no separate column:

| Canonical type      | Stored as                                             |
| ------------------- | ----------------------------------------------------- |
| `founder`           | `long_term` + `scope=manual` + `metadata.category`    |
| `business`          | `long_term` + `scope=manual` + `metadata.category`    |
| `crm`               | `long_term` + `scope=manual` + `metadata.category`    |
| `knowledge`         | `long_term` + `scope=manual` + `metadata.category`    |
| `conversation`      | `working` + `scope=conversation`                      |
| `research`          | `working` + `scope=research`                          |
| `workflow`          | `working` + `scope=workflow`                          |
| `shared_context`    | `working` + `scope=shared_context`                    |

`long_term` memories are durable; `working` memories are TTL-pruned by the
memory cleanup worker (see below).

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

Manual creates write the row verbatim (no dedup, no skip rules). The M4 write
path with dedup/skip rules is `capture_memory`, used by AI callers — never this
endpoint.

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

## M4 retrieval pipeline (service-internal)

`MemoryService.retrieve_context(org, ...)` feeds the AI system prompt. Gated on
`AI_MEMORY_ENABLED`; the AI service fails open (no memory context) on error.

1. Fetch an org-scoped candidate pool (`list_ranked`, newest first, bounded to
   `min(max(retrieval_limit × 4, 1), 100)` rows).
2. Rank deterministically — no embeddings or LLM calls:
   - recency (linear decay over 30 days), weight 0.4;
   - importance (`importance / 5`), weight 0.3;
   - provenance match against the query scope (`±0.2`), weight 0.2;
   - total clipped to `[0, 1]`, ties broken newest-first, and anything below
     the `0.2` threshold is dropped.
3. Assemble a plain-text block of at most `MEMORY_CONTEXT_MAX_CHARS` (default
   2500) characters and `MEMORY_RETRIEVAL_LIMIT` (default 10) entries:

   ```
   [founder] Founder note
   Prefers async comms.
   ```

The block is injected into the system prompt between the capabilities and the
`=== AVAILABLE TOOLS ===` sections.

## M4 capture path (service-internal)

`MemoryService.capture_memory` is the AI write path:

- skipped (returns nothing) when the trimmed content is under 10 chars or
  `importance` is below 2;
- working memories are de-duplicated: an entry with the same normalized content
  created within the last 24h returns the existing row instead of writing;
- a missing `scope` is inferred from the source context (default `research`).

## M4 promotion (service-internal)

`MemoryService.promote_to_knowledge(org, memory_id, category)` copies a memory
into a durable `knowledge_items` row. There is no API route for this:

- blank `category` → `400 knowledge.category_required`;
- duplicate-guarded: an item already linked to the memory via
  `source_memory_id` is returned unchanged;
- provenance is recorded in the item `metadata` (`origin: "memory"`,
  `source_memory_id`); the title falls back to the memory title, then
  `"Knowledge"`.

## Memory cleanup worker

Expired `working` memories are deleted by the standalone memory worker
(`python -m app.workers.memory_worker`), config-gated on
`MEMORY_CLEANUP_ENABLED` (default true):

- every `MEMORY_CLEANUP_INTERVAL_SECONDS` (default 3600), rows older than
  `MEMORY_WORKING_TTL_DAYS` are swept in org-scoped batches of
  `MEMORY_CLEANUP_BATCH_SIZE` (default 500), oldest-first;
- up to 1000 orgs are visited per tick; the sweep is idempotent and restart-safe
  (next tick resumes any remaining orgs); one commit per tick inside a
  `SET LOCAL statement_timeout` guard;
- `long_term` memory is never eligible; no promotion happens here.

Observability: counter `agencyos.memory.cleanup.expired_total`, histogram
`agencyos.memory.cleanup.duration_seconds`, plus the standard `worker_health`
heartbeat (`worker_type=memory`). See `docs/operations/admin-guide.md`.

## Authentication

`Authorization: Bearer <token>`. Errors use the standard envelope.
