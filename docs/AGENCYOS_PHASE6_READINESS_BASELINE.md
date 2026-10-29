# AgencyOS — Phase 6 Readiness Baseline

**Status:** Readiness baseline only. Phase 6 implementation is NOT authorized and was NOT started.

## Phase 6 goals (as documented in repository plans)

Phase 6 ("AI Brain / Agent runtime") builds on the existing M5/M8/M9/M11 foundations:
- Agent runtime executor lifecycle and queue draining.
- Durable AI memories and knowledge items.
- Founder AI assistant surfaces.
- Intelligence/growth triage.
- Outreach dispatch via n8n.

## Proposed minimum first increment (Option A direction)

A small, bounded first increment reusing existing capabilities:
1. Reuse `AgentService` run lifecycle (`create_run`, `get_run`, idempotency) — already implemented and tested (`test_m11_ai_run.py`).
2. Reuse `MemoryService` capture/retrieve/promote — already implemented and tested.
3. Reuse `ToolRegistry` + `ToolAuthorization` — already implemented and tested.
4. Reuse `OutreachService` + the now-secured write endpoints — tested (H2).
5. Frontend: a single founder-facing "AI run" trigger + status view, reusing existing `/ai/run` and `/ai/dispatch` endpoints.

## Existing functionality to reuse (do not rebuild)

- Backend: `app/ai/*`, `app/agents/*`, `app/services/agent_service.py`, `app/services/memory_service.py`, `app/tools/*`, `app/core/permissions.py`, outreach endpoints (H2-secured).
- Frontend: existing app shell, auth, API client (`frontend/src/lib/api.ts`).
- Infra: Postgres + Redis already provisioned in CI/compose.

## Required backend contracts

- `POST /api/v1/ai/run` (permission `ai_run`), `POST /api/v1/ai/dispatch` (permission `lead_write`).
- `GET /api/v1/agents/runs`, `GET /api/v1/agents/runs/{id}`, `POST /api/v1/agents/runs/{id}/cancel`.
- `GET/POST /api/v1/memory`, `GET/POST /api/v1/memory/knowledge`.
- No new endpoints required for the minimum increment.

## Permission requirements

- `ai_run` (granted to non-viewer write roles), `agent_read`/`agent_manage`, `memory_read`/`memory_write`, `lead_write` (already secured).
- VIEWER must remain read-only; no new grants to VIEWER.

## Test acceptance criteria (for when Phase 6 is authorized)

- Unit tests for any new frontend component (Vitest).
- Integration test for the AI run lifecycle against real Postgres (reuse `test_m11_ai_run.py` pattern).
- Authorization tests for new/changed endpoints (reuse `test_*_rbac.py` pattern).
- E2E smoke for the trigger→status flow with synthetic data.
- `make ci` green on the Phase 6 branch.

## Deferred capabilities (explicitly out of minimum scope)

- Redis queue implementation, cross-instance locking.
- n8n cancellation/retry policies.
- Operations dashboard, notifications redesign.
- Advanced memory research/usage surfaces.
- Zod/Vite/Vitest toolchain migration (separate follow-up).

## Known risks and dependencies

- AI budgets (`AI_ORG_DAILY_TOKEN_BUDGET`, `AI_ORG_DAILY_COST_BUDGET_USD`) default to 0 = fail closed; must be set before enabling AI execution.
- Feature flags (`AGENT_RUNTIME_ENABLED`, `AI_MEMORY_ENABLED`, etc.) default OFF; must be enabled deliberately.
- n8n must be configured (`N8N_BASE_URL`) for outreach dispatch to function.
- LLM provider keys must be provisioned.

## Suggested implementation order

1. Enable `AGENT_RUNTIME_ENABLED` in a dev environment and verify the existing worker drains runs.
2. Add the minimal frontend trigger + status view.
3. Add authorization + integration tests.
4. Gate behind `FOUNDER_ASSISTANT_ENABLED` for the founder surface.
5. Only then consider broader AI Brain features.

## Confirmation

No Phase 6 feature code was written, no migration was created, and no Phase 6 branch was created during this readiness audit.
