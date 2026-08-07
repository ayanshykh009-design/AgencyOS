-- agent_runs: per-run execution records for the agent runtime (Phase 5D)
CREATE TABLE IF NOT EXISTS public.agent_runs (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  agent_name      text NOT NULL,
  status          public.agent_run_status NOT NULL DEFAULT 'queued',
  trigger         public.agent_run_trigger NOT NULL DEFAULT 'manual',
  workflow_id     uuid REFERENCES public.workflows (id) ON DELETE SET NULL,
  input           jsonb NOT NULL DEFAULT '{}',
  output          jsonb,
  error           text,
  duration_ms     integer,
  cost            numeric(18, 6) NOT NULL DEFAULT 0,
  started_at      timestamptz,
  finished_at     timestamptz,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT chk_agent_runs_agent_name_not_blank CHECK (length(btrim(agent_name)) > 0),
  CONSTRAINT chk_agent_runs_duration_nonneg CHECK (duration_ms IS NULL OR duration_ms >= 0),
  CONSTRAINT chk_agent_runs_cost_nonneg CHECK (cost >= 0)
);

CREATE INDEX IF NOT EXISTS idx_agent_runs_org_status
  ON public.agent_runs (organization_id, status);
CREATE INDEX IF NOT EXISTS idx_agent_runs_org_agent_created
  ON public.agent_runs (organization_id, agent_name, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_runs_org_created
  ON public.agent_runs (organization_id, created_at DESC);
-- FK support (workflow-triggered runs).
CREATE INDEX IF NOT EXISTS idx_agent_runs_org_workflow
  ON public.agent_runs (organization_id, workflow_id);
-- Configurable-retention sweep.
CREATE INDEX IF NOT EXISTS idx_agent_runs_created_retention
  ON public.agent_runs (created_at);

DROP TRIGGER IF EXISTS trg_agent_runs_updated_at ON public.agent_runs;
CREATE TRIGGER trg_agent_runs_updated_at
  BEFORE UPDATE ON public.agent_runs
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.agent_runs ENABLE ROW LEVEL SECURITY;
