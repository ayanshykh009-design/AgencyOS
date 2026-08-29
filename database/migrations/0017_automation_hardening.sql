-- =====================================================================
-- 0017_automation_hardening.sql
-- Phase 5C: automation foundation hardening.
--
--   * execution_event_type            — labels for the append-only timeline
--   * execution_events                — per-attempt execution timeline (immutable)
--   * worker_health                   — worker instance heartbeats
--   * system_settings                 — operator key/value store (automation
--                                       kill switch + pause metadata)
--   * workflow_executions             — + cancel_requested_at,
--                                       + cancelled_by_user_id,
--                                       + idempotency_key (unique per org),
--                                       + (org, created_at DESC) list index,
--                                       + partial cancel-pending index
--   * activity_event_type             — extended with automation_paused /
--                                       automation_resumed
--
-- Backward compatibility:
--   * additive columns only (nullable; no table rewrite)
--   * CREATE TABLE / INDEX IF NOT EXISTS are idempotent
--   * enum creation guarded by pg_type existence checks
--   * safe to run multiple times; zero data loss
-- =====================================================================

-- ---------------------------------------------------------------------
-- execution_event_type: labels for the append-only execution timeline.
-- ---------------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'public' AND t.typname = 'execution_event_type'
  ) THEN
    CREATE TYPE public.execution_event_type AS ENUM (
      'queued', 'started', 'adapter_dispatched', 'adapter_returned',
      'step_started', 'step_completed', 'step_failed',
      'retrying', 'succeeded', 'failed', 'cancelled', 'timed_out',
      'timeout_guard'
    );
  END IF;
END;
$$;

-- ---------------------------------------------------------------------
-- extend activity_event_type with automation control events
-- ---------------------------------------------------------------------
DO $$
DECLARE
  v_label text;
BEGIN
  FOREACH v_label IN ARRAY ARRAY[
    'automation_paused', 'automation_resumed'
  ]
  LOOP
    IF NOT EXISTS (
      SELECT 1
      FROM pg_enum e
      JOIN pg_type t ON t.oid = e.enumtypid
      JOIN pg_namespace n ON n.oid = t.typnamespace
      WHERE n.nspname = 'public'
        AND t.typname = 'activity_event_type'
        AND e.enumlabel = v_label
    ) THEN
      EXECUTE format('ALTER TYPE public.activity_event_type ADD VALUE IF NOT EXISTS %L', v_label);
    END IF;
  END LOOP;
END;
$$;

-- ---------------------------------------------------------------------
-- execution_events: immutable per-attempt execution timeline.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.execution_events (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  workflow_id     uuid NOT NULL REFERENCES public.workflows (id) ON DELETE CASCADE,
  execution_id    uuid NOT NULL REFERENCES public.workflow_executions (id) ON DELETE CASCADE,
  attempt         integer NOT NULL DEFAULT 0,
  event_type      public.execution_event_type NOT NULL,
  metadata        jsonb NOT NULL DEFAULT '{}',
  occurred_at     timestamptz NOT NULL DEFAULT now(),
  created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_execution_events_execution_occurred
  ON public.execution_events (execution_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_execution_events_org_workflow_occurred
  ON public.execution_events (organization_id, workflow_id, occurred_at);
-- Supports the retention sweep's global chunked DELETE (occurred_at ordering).
CREATE INDEX IF NOT EXISTS idx_execution_events_occurred_at
  ON public.execution_events (occurred_at);

ALTER TABLE public.execution_events ENABLE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------
-- worker_health: per-instance heartbeat rows for the automation workers.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.worker_health (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  worker_type       text NOT NULL CHECK (worker_type IN ('execution', 'credential')),
  instance_id       uuid NOT NULL,
  pid               integer NOT NULL,
  hostname          text NOT NULL DEFAULT '',
  loop_ok           boolean NOT NULL DEFAULT true,
  last_error        text,
  counters          jsonb NOT NULL DEFAULT '{}',
  last_heartbeat_at timestamptz NOT NULL DEFAULT now(),
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_worker_health_type_instance
  ON public.worker_health (worker_type, instance_id);
CREATE INDEX IF NOT EXISTS idx_worker_health_type_heartbeat
  ON public.worker_health (worker_type, last_heartbeat_at DESC);
-- Supports the retention sweep's pruning of long-dead heartbeat rows.
CREATE INDEX IF NOT EXISTS idx_worker_health_heartbeat
  ON public.worker_health (last_heartbeat_at);

DROP TRIGGER IF EXISTS trg_worker_health_updated_at
  ON public.worker_health;
CREATE TRIGGER trg_worker_health_updated_at
  BEFORE UPDATE ON public.worker_health
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.worker_health ENABLE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------
-- system_settings: operator-controlled key/value settings (global).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.system_settings (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  key                text NOT NULL UNIQUE CHECK (length(btrim(key)) > 0),
  value              jsonb NOT NULL DEFAULT '{}',
  updated_by_user_id uuid REFERENCES public.users (id) ON DELETE SET NULL,
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS trg_system_settings_updated_at
  ON public.system_settings;
CREATE TRIGGER trg_system_settings_updated_at
  BEFORE UPDATE ON public.system_settings
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.system_settings ENABLE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------
-- workflow_executions: queue-hardening columns (additive).
-- ---------------------------------------------------------------------
ALTER TABLE public.workflow_executions
  ADD COLUMN IF NOT EXISTS cancel_requested_at timestamptz;

ALTER TABLE public.workflow_executions
  ADD COLUMN IF NOT EXISTS cancelled_by_user_id uuid
  REFERENCES public.users (id) ON DELETE SET NULL;

ALTER TABLE public.workflow_executions
  ADD COLUMN IF NOT EXISTS idempotency_key text;

CREATE UNIQUE INDEX IF NOT EXISTS uq_workflow_executions_org_idempotency
  ON public.workflow_executions (organization_id, idempotency_key)
  WHERE idempotency_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_workflow_executions_org_created
  ON public.workflow_executions (organization_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_workflow_executions_cancel_pending
  ON public.workflow_executions (cancel_requested_at)
  WHERE cancel_requested_at IS NOT NULL;

-- =====================================================================
-- ROLLBACK
-- =====================================================================
-- DROP INDEX IF EXISTS public.idx_worker_health_heartbeat;
-- DROP INDEX IF EXISTS public.idx_execution_events_occurred_at;
-- DROP INDEX IF EXISTS public.idx_workflow_executions_cancel_pending;
-- DROP INDEX IF EXISTS public.idx_workflow_executions_org_created;
-- DROP INDEX IF EXISTS public.uq_workflow_executions_org_idempotency;
-- ALTER TABLE public.workflow_executions DROP COLUMN IF EXISTS idempotency_key;
-- ALTER TABLE public.workflow_executions DROP COLUMN IF EXISTS cancelled_by_user_id;
-- ALTER TABLE public.workflow_executions DROP COLUMN IF EXISTS cancel_requested_at;
-- DROP TABLE IF EXISTS public.system_settings;
-- DROP TABLE IF EXISTS public.worker_health;
-- DROP TABLE IF EXISTS public.execution_events;
-- ALTER TYPE public.activity_event_type DROP VALUE 'automation_resumed';
-- ALTER TYPE public.activity_event_type DROP VALUE 'automation_paused';
-- DROP TYPE IF EXISTS public.execution_event_type;
-- =====================================================================
