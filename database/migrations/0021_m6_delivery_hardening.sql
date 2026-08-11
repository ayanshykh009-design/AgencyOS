-- =====================================================================
-- 0021_m6_delivery_hardening.sql
-- Phase M6: Founder Communication & Delivery Layer — hardening.
--
--   * approval_requests.gate_handled_at     — the approval-gate worker stamps
--                                             this when a terminal decision
--                                             has been applied to the gated
--                                             workflow execution
--   * worker_health constraint              — admit 'delivery' and
--                                             'approval_gate' (plus the
--                                             existing agent/memory types that
--                                             the M5/M6 workers already
--                                             heartbeat with)
--
-- Backward compatibility:
--   * additive column + index only; constraint re-created idempotently
--   * safe to run multiple times; zero data loss
-- =====================================================================

-- ---------------------------------------------------------------------
-- approval_requests.gate_handled_at: stamped by the gate worker once the
-- terminal decision (approved/denied/expired/cancelled) has been applied to
-- the linked workflow execution. NULL means the gate is still open.
-- ---------------------------------------------------------------------
ALTER TABLE public.approval_requests
  ADD COLUMN IF NOT EXISTS gate_handled_at timestamptz;

-- Gate-worker sweep: terminal requests whose gate has not been handled yet.
CREATE INDEX IF NOT EXISTS idx_approval_requests_gate_handled
  ON public.approval_requests (status)
  WHERE gate_handled_at IS NULL AND workflow_execution_id IS NOT NULL;

-- ---------------------------------------------------------------------
-- worker_health.worker_type: extend the closed set to admit the delivery
-- worker ('delivery') and the approval-gate worker ('approval_gate') plus
-- the agent/memory worker types that heartbeat rows with today (previously
-- rejected by the 0017 CHECK constraint, so those heartbeats silently
-- failed). Re-created idempotently: drops the old inline constraint
-- (auto-named worker_health_worker_type_check) if it still exists, then
-- adds the explicit named constraint when missing.
-- ---------------------------------------------------------------------
DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'worker_health_worker_type_check'
      AND conrelid = 'public.worker_health'::regclass
  ) THEN
    ALTER TABLE public.worker_health DROP CONSTRAINT worker_health_worker_type_check;
  END IF;
END;
$$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'chk_worker_health_type'
      AND conrelid = 'public.worker_health'::regclass
  ) THEN
    ALTER TABLE public.worker_health
      ADD CONSTRAINT chk_worker_health_type
      CHECK (worker_type IN ('execution', 'credential', 'delivery', 'approval_gate', 'agent', 'memory'));
  END IF;
END;
$$;

-- =====================================================================
-- ROLLBACK
-- =====================================================================
-- DROP INDEX IF EXISTS public.idx_approval_requests_gate_handled;
-- ALTER TABLE public.approval_requests DROP COLUMN IF EXISTS gate_handled_at;
-- ALTER TABLE public.worker_health DROP CONSTRAINT IF EXISTS chk_worker_health_type;
-- ALTER TABLE public.worker_health
--   ADD CONSTRAINT worker_health_worker_type_check
--   CHECK (worker_type IN ('execution', 'credential'));
-- =====================================================================
