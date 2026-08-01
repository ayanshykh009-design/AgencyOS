# Workflow templates

Reusable n8n building blocks that workflows are assembled from.

Add one JSON export per template, e.g.:

- `supabase-upsert.json` — upsert rows into a Supabase table
- `http-with-retry.json` — resilient HTTP call with retry/backoff
- `prompt-render.json` — render a versioned prompt from `prompts/` via the
  OpenAI / Anthropic nodes

Templates should be parameterized (via workflow settings / env vars) so they
can be reused across workflows without edits.
