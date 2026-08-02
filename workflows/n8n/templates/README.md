# Workflow templates

Reusable n8n building blocks that workflows are assembled from. Each template is
a valid standalone workflow JSON (with a manual trigger for testing) that gets
copied into workflows and wired to the appropriate trigger.

| File | Purpose |
| ---- | ------- |
| `http-with-retry.json` | Resilient HTTP call with `retryOnFail` (3 tries, 2s backoff). Input: `url`. |
| `supabase-upsert.json` | Upsert rows into a Supabase table via PostgREST (`Prefer: resolution=merge-duplicates`). Input: `table`, `rows`. |
| `prompt-render.json` | Render a versioned prompt from `prompts/` via OpenAI. Input: `promptPath`, `userMessage`, optional `model`. |

Inputs are consumed from the incoming item (`$json.<field>`) so templates can be
chained behind any trigger. Secrets come from `$env` / n8n credentials — see the
parent `README.md` for the environment variable table.
