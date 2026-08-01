# n8n workflows

Production automation for lead sourcing, enrichment, outreach execution, and
reporting. Workflows are stored as version-controlled JSON exports.

## Workflow naming

`<domain>-<purpose>.json`

Examples (create when implemented):

- `lead-sourcing-cleansing.json` — dedupe/clean imported lead lists
- `lead-enrichment-enrichment.json` — enrich prospects (Apollo/Hunter/Clay)
- `outreach-dispatch.json` — push personalized drafts to SMTP/SendGrid
- `reporting-summary.json` — aggregate reply metrics into Supabase

## Templates

Reusable building blocks in `templates/` (e.g. a standardized "HTTP to
Supabase upsert" template) that get copied into workflows.

## Local runtime

The `.n8n/` directory is mounted from `workflows/n8n` in docker-compose and is
git-ignored — it holds runtime state and encrypted credentials.
