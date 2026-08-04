-- =====================================================================
-- 0014_schedule_last_fired.sql
-- Schedule dispatcher support for workflow triggers.
--
-- Adds last_fired_at to workflow_triggers: the UTC timestamp of the last
-- successfully claimed cron tick, used by the schedule dispatcher for
-- restart-safe, idempotent dedup (a tick can never dispatch twice, even
-- across worker instances/restarts).
--
-- Backward compatibility:
--   * additive column (nullable, no DEFAULT, no table rewrite, no row mutation)
--   * CREATE INDEX IF NOT EXISTS is idempotent
--   * safe to run multiple times; zero data loss
-- =====================================================================

ALTER TABLE public.workflow_triggers
  ADD COLUMN IF NOT EXISTS last_fired_at timestamptz;

CREATE INDEX IF NOT EXISTS idx_workflow_triggers_schedule_due
  ON public.workflow_triggers (last_fired_at)
  WHERE trigger_type = 'schedule' AND enabled;
