-- =====================================================================
-- 0028_m11_ai_run_trace.sql
-- Phase M11: AI Brain hardening + run orchestration.
--
--   * add the 'ai_run' value to the existing native enum
--     ``agent_run_trigger`` (PG12+: ALTER TYPE ADD VALUE is safe inside a
--     transaction once no later statement in the same txn needs the value),
--   * add ``trace_id uuid`` to ``agent_runs`` so an AI run is traceable from
--     the originating HTTP request through the Brain + tool dispatch to the
--     final result (M11-C).
--
-- Backward compatibility: additive only (new enum value + nullable column).
-- =====================================================================

-- New trigger source for runs created via the unified /api/v1/ai/run surface.
ALTER TYPE public.agent_run_trigger ADD VALUE IF NOT EXISTS 'ai_run';

ALTER TABLE public.agent_runs ADD COLUMN IF NOT EXISTS trace_id uuid;

-- Trace lookups (cross-request correlation / audit).
CREATE INDEX IF NOT EXISTS idx_agent_runs_trace_id
  ON public.agent_runs (trace_id);
