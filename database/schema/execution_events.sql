-- execution_events: immutable per-attempt execution timeline (Phase 5C)
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

CREATE INDEX idx_execution_events_execution_occurred
  ON public.execution_events (execution_id, occurred_at);
CREATE INDEX idx_execution_events_org_workflow_occurred
  ON public.execution_events (organization_id, workflow_id, occurred_at);
-- Supports the retention sweep's global chunked DELETE (occurred_at ordering).
CREATE INDEX idx_execution_events_occurred_at
  ON public.execution_events (occurred_at);

ALTER TABLE public.execution_events ENABLE ROW LEVEL SECURITY;
