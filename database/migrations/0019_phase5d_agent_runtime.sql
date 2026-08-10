-- =====================================================================
-- 0019_phase5d_agent_runtime.sql
-- M5: Agent Runtime hardening on agent_runs (additive only).
--
--   * agent_runs                       + cancel_requested_at
--                                      + cancelled_by_user_id
--                                      + idempotency_key (unique per org)
--                                      + partial cancel-pending index
--
-- Mirrors the 0017 queue-hardening columns on workflow_executions so the M5
-- worker can offer the same guarantees for agent runs: at-least-once dispatch
-- with idempotent re-queue, and cooperative cancellation of in-flight runs.
--
-- Backward compatibility:
--   * additive columns only (nullable; no table rewrite)
--   * CREATE INDEX IF NOT EXISTS are idempotent
--   * safe to run multiple times; zero data loss
-- =====================================================================

ALTER TABLE public.agent_runs
  ADD COLUMN IF NOT EXISTS cancel_requested_at timestamptz;

ALTER TABLE public.agent_runs
  ADD COLUMN IF NOT EXISTS cancelled_by_user_id uuid
  REFERENCES public.users (id) ON DELETE SET NULL;

ALTER TABLE public.agent_runs
  ADD COLUMN IF NOT EXISTS idempotency_key text;

-- Re-queueing a run with the same (org, key) must not create a duplicate run;
-- mirrors uq_workflow_executions_org_idempotency.
CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_runs_org_idempotency
  ON public.agent_runs (organization_id, idempotency_key)
  WHERE idempotency_key IS NOT NULL;

-- The worker's in-flight cancellation sweep targets runs flagged for cancel.
CREATE INDEX IF NOT EXISTS idx_agent_runs_cancel_pending
  ON public.agent_runs (cancel_requested_at)
  WHERE cancel_requested_at IS NOT NULL;

-- =====================================================================
-- ROLLBACK
-- =====================================================================
-- DROP INDEX IF EXISTS public.idx_agent_runs_cancel_pending;
-- DROP INDEX IF EXISTS public.uq_agent_runs_org_idempotency;
-- ALTER TABLE public.agent_runs DROP COLUMN IF EXISTS idempotency_key;
-- ALTER TABLE public.agent_runs DROP COLUMN IF EXISTS cancelled_by_user_id;
-- ALTER TABLE public.agent_runs DROP COLUMN IF EXISTS cancel_requested_at;
-- =====================================================================
