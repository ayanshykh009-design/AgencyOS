-- Extend worker_health.worker_type to admit the M8/M9 worker types.
--
-- Migration 0021 extended the closed set to
-- ('execution','credential','delivery','approval_gate','agent','memory') but the
-- founder (M8) and intelligence triage (M9) workers heartbeat with
-- ('founder_action','intelligence_triage'), which the CHECK constraint still
-- rejects. Any such heartbeat raises a CHECK violation that escapes the worker
-- loop's unguarded ``finally`` heartbeat and the worker process dies on its
-- first sweep, so the M8 and M9 automation paths are dead on arrival once those
-- features are enabled.
--
-- Re-created idempotently (replay/fresh-install safe): drops the existing named
-- constraint (whatever its current allowed-set) and the legacy auto-named
-- 0017 constraint if either is present, then adds the named constraint with the
-- full worker-type set.
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
  IF EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'chk_worker_health_type'
      AND conrelid = 'public.worker_health'::regclass
  ) THEN
    ALTER TABLE public.worker_health DROP CONSTRAINT chk_worker_health_type;
  END IF;
END;
$$;

ALTER TABLE public.worker_health
  ADD CONSTRAINT chk_worker_health_type
  CHECK (worker_type IN (
    'execution', 'credential', 'delivery', 'approval_gate',
    'agent', 'memory', 'founder_action', 'intelligence_triage'
  ));

-- =====================================================================
-- ROLLBACK
-- =====================================================================
-- ALTER TABLE public.worker_health DROP CONSTRAINT IF EXISTS chk_worker_health_type;
-- ALTER TABLE public.worker_health
--   ADD CONSTRAINT chk_worker_health_type
--   CHECK (worker_type IN ('execution', 'credential', 'delivery', 'approval_gate', 'agent', 'memory'));
-- =====================================================================
