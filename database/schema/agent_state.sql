-- agent_state: rolling health bookkeeping for the agent runtime (Phase 5D)
CREATE TABLE IF NOT EXISTS public.agent_state (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id   uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  agent_name        text NOT NULL,
  status            public.agent_state_status NOT NULL DEFAULT 'active',
  health            public.agent_health NOT NULL DEFAULT 'healthy',
  queue_depth       integer NOT NULL DEFAULT 0,
  total_runs        integer NOT NULL DEFAULT 0,
  average_runtime_ms numeric(12, 2) NOT NULL DEFAULT 0,
  average_cost      numeric(18, 6) NOT NULL DEFAULT 0,
  last_execution    timestamptz,
  last_error        text,
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT chk_agent_state_agent_name_not_blank CHECK (length(btrim(agent_name)) > 0),
  CONSTRAINT chk_agent_state_queue_depth_nonneg CHECK (queue_depth >= 0),
  CONSTRAINT chk_agent_state_total_runs_nonneg CHECK (total_runs >= 0),
  CONSTRAINT chk_agent_state_avg_runtime_nonneg CHECK (average_runtime_ms >= 0),
  CONSTRAINT chk_agent_state_avg_cost_nonneg CHECK (average_cost >= 0)
);

-- One state row per agent within an organization.
CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_state_org_agent
  ON public.agent_state (organization_id, agent_name);
-- Global fleet-health scans (operator monitoring).
CREATE INDEX IF NOT EXISTS idx_agent_state_status_health
  ON public.agent_state (status, health);

DROP TRIGGER IF EXISTS trg_agent_state_updated_at ON public.agent_state;
CREATE TRIGGER trg_agent_state_updated_at
  BEFORE UPDATE ON public.agent_state
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.agent_state ENABLE ROW LEVEL SECURITY;
