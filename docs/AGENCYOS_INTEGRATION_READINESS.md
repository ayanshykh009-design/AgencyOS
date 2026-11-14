# AgencyOS — Integration Readiness

## Email (SMTP)

- **Status:** Implemented (password reset, email verification, MFA flows) but **unconfigured** by default (`SMTP_HOST=` empty).
- **Config:** `SMTP_HOST/PORT/USERNAME/PASSWORD/FROM_EMAIL/USE_TLS`, `EMAIL_VERIFICATION_ENABLED` (default false), `PASSWORD_RESET_ENABLED` (default true).
- **Validation:** production requires SMTP when verification/reset enabled (fail-closed).
- **Safe smoke test:** not run (no SMTP configured). Password-reset flow is enumeration-safe (covered by tests).
- **Decision:** Deferred for initial internal use; can be enabled when SMTP is provisioned. No real emails sent during this audit.

## WhatsApp

- **Status:** No dedicated WhatsApp provider integration found in `app/` (outreach channel enum includes `whatsapp`, but no provider client). Not configured.
- **Decision:** Deferred. Channel is modeled but no live provider wiring.

## n8n

- **Status:** Implemented client (`app/services/n8n_client.py`, `app/tools/n8n_tool.py`) with health check, webhook trigger, sanitized error handling (covered by `test_n8n_client.py`).
- **Config:** `N8N_BASE_URL` (empty by default). `WEBHOOK_SECRET` for inbound webhooks.
- **Safety:** `N8N_BASE_URL` empty causes dispatch to fail with a clear error; no outbound calls made during this audit.
- **Decision:** Deferred until `N8N_BASE_URL` is provisioned; outreach dispatch returns a controlled error otherwise.

## AI providers (OpenAI / Anthropic / Gemini / compatible / Ollama / DeepSeek)

- **Status:** Implemented provider layer (`app/llm/providers/*`) with retry, timeout, tool calling; covered by `test_providers.py`.
- **Config:** `LLM_PROVIDER`, `LLM_DEFAULT_MODEL`, provider API keys (all empty by default), `LLM_TIMEOUT_SECONDS`, budgets.
- **Safety:** Budgets default to 0 = fail closed; no paid calls made during this audit. `test_llm.py` uses mocks.
- **Decision:** Configurable but not provisioned; AI execution is disabled by default budgets. Provision keys + positive budgets to enable.

## MCP / tools

- **Status:** Implemented tool registry + MCP resource reading (opencode tooling). Covered by `test_tools.py`, `test_tool_authorization.py`.
- **Decision:** Ready for internal use; no external credentials required for the built-in tools.

## Calendar

- **Status:** No dedicated calendar provider integration found beyond the task/calendar domain models. Frontend calendar surface (if present) is not backed by an external provider.
- **Decision:** Deferred/not required for initial internal workflows.

## File / object storage

- **Status:** Local filesystem only (`storage/uploads`, `storage/logs`). Supabase storage not wired by default.
- **Decision:** Acceptable for single-instance internal use; object storage needed before multi-instance/production.

## Summary

No integration is falsely marked PASS. Email, WhatsApp, n8n, and AI providers are all **unconfigured** and their absence is explicitly accepted for the initial internal scope (feature flags default OFF). MCP/tools and local file storage are **ready**.
