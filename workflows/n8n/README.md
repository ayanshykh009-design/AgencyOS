# n8n workflows

Production automation for lead sourcing, enrichment, outreach execution, and
reporting. Workflows are stored as version-controlled JSON exports.

## Workflows

| File | Trigger | Purpose |
| ---- | ------- | ------- |
| `workflows/lead-sourcing-cleansing.json` | Webhook `POST /lead-sourcing` | Clean/normalize inbound prospects and ingest into AgencyOS via `POST /api/v1/webhooks/leads` (server-side dedupe). |
| `workflows/lead-enrichment-enrichment.json` | Webhook `POST /lead-enrichment` | Enrich a prospect (Apollo People Match) then ingest via the same webhook. |
| `workflows/outreach-dispatch.json` | Webhook `POST /outreach-dispatch` | Render a personalized cold email from `prompts/cold-email/v1.0.0-ice-breaker.md` and send via SMTP. |
| `workflows/reporting-summary.json` | Cron `0 9 * * 1` (weekly) | Fetch `GET /api/v1/dashboard/summary` and email a pipeline summary. |

All workflows use only core n8n nodes. Node parameters are pinned to explicit
`typeVersion`s so re-imports stay stable.

## Environment variables

Workflows reference secrets through `$env` — never hardcode credentials:

| Variable | Used by |
| -------- | ------- |
| `AGENCYOS_BASE_URL` | All workflows (API base, e.g. `https://api.example.com`) |
| `AGENCYOS_ORG_SLUG` | Sourcing / enrichment |
| `AGENCYOS_WEBHOOK_SECRET` | Sourcing / enrichment (must match backend `WEBHOOK_SECRET`) |
| `AGENCYOS_PROMPTS_DIR` | Dispatch, `templates/prompt-render.json` (absolute path to `prompts/`) |
| `OPENAI_API_KEY` | Dispatch, `templates/prompt-render.json` |
| `APOLLO_API_KEY` | Enrichment |
| `AGENCYOS_BOT_ACCESS_TOKEN` | Reporting (bearer token of a bot user with dashboard access) |
| `OUTREACH_FROM_EMAIL` / `REPORTING_TO_EMAIL` | Dispatch / reporting |
| `SUPABASE_REST_URL` / `SUPABASE_SERVICE_KEY` | `templates/supabase-upsert.json` |

The SMTP credential (`AgencyOS SMTP`) and any provider credentials must be
created in the n8n instance — the exported credential IDs are placeholders that
are re-assigned on import.

## Templates

Reusable building blocks in `templates/`:

| Template | Purpose |
| -------- | ------- |
| `templates/http-with-retry.json` | HTTP request with `retryOnFail` (3 tries, 2s backoff). |
| `templates/supabase-upsert.json` | PostgREST upsert (`resolution=merge-duplicates`) of `$json.rows` into `$json.table`. |
| `templates/prompt-render.json` | Load a versioned prompt from `prompts/` and render it via OpenAI. |

## Importing

1. Start the stack (`make up`) and log into n8n at `http://localhost:5678`.
2. Create the **AgencyOS SMTP** credential (and provider credentials).
3. Import a workflow JSON via *Workflows → Import from file*, then set the
   environment variables above on the n8n container and re-check node config.

## Validation

Exports are checked structurally by CI (`backend/tests/unit/test_workflow_definitions.py`):
JSON parses, required top-level fields exist, node ids are unique, and every
connection references a real node. Full node-schema validation requires
importing into an n8n instance — do that before activating a workflow.

## Local runtime

The `.n8n/` directory is mounted from `workflows/n8n` in docker-compose and is
git-ignored — it holds runtime state and encrypted credentials.
