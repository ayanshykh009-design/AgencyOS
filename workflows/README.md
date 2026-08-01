# Workflows — n8n Automation

Automation layer for the Agency Operating System. n8n orchestrates external
data movement and integration tasks that don't belong in the FastAPI backend.

## Folder layout

| Path                    | Purpose                                                        |
| ----------------------- | -------------------------------------------------------------- |
| `n8n/workflows/`        | Importable n8n workflow JSON exports (one file per workflow).  |
| `n8n/templates/`        | Reusable workflow templates / sub-workflow building blocks.    |
| `n8n/.n8n/`             | n8n runtime data directory (created on start, git-ignored).    |

## Conventions

- **Export workflows as JSON** (`File > Export`) into `n8n/workflows/`
  following `<domain>-<name>.json`, e.g. `lead-enrichment-apollo.json`.
- Keep workflow files under version control; never commit `n8n/.n8n/`
  (contains credentials/encryption keys).
- Secrets used by workflows come from n8n env vars / credentials store —
  never hardcode API keys inside workflow JSON.

## Getting started

The n8n service is defined in `docker-compose.yml`. Start it with:

```bash
make up          # starts postgres + n8n
# UI: http://localhost:5678
```

Import saved workflows from the n8n dashboard (`Workflows > Import from file`).
