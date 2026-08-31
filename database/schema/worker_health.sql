-- worker_health: per-instance heartbeat rows for the automation workers (Phase 5C)
CREATE TABLE IF NOT EXISTS public.worker_health (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  worker_type       text NOT NULL
                    CONSTRAINT chk_worker_health_type
                    CHECK (worker_type IN ('execution', 'credential', 'delivery', 'approval_gate', 'agent', 'memory', 'founder_action', 'intelligence_triage')),
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

CREATE UNIQUE INDEX uq_worker_health_type_instance
  ON public.worker_health (worker_type, instance_id);
CREATE INDEX idx_worker_health_type_heartbeat
  ON public.worker_health (worker_type, last_heartbeat_at DESC);
-- Supports the retention sweep's pruning of long-dead heartbeat rows.
CREATE INDEX idx_worker_health_heartbeat
  ON public.worker_health (last_heartbeat_at);

CREATE TRIGGER trg_worker_health_updated_at
  BEFORE UPDATE ON public.worker_health
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.worker_health ENABLE ROW LEVEL SECURITY;
