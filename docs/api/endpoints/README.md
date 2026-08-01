# Endpoint Reference

One file per endpoint group, e.g.:

- `health.md` — liveness probes
- `auth.md` — register, login, refresh, me (pending implementation)
- `campaigns.md` — CRUD for outreach campaigns (pending implementation)
- `prospects.md` — prospect management (pending implementation)

Each file documents: request/response schemas, auth requirements, error codes,
and example payloads. Implement alongside the endpoints — docs rot fast if
written late.
