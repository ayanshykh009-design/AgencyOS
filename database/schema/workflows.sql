-- workflows: tenant-scoped workflow registry with execution config
CREATE TABLE IF NOT EXISTS public.workflows (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id      uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  name                 text NOT NULL CHECK (length(btrim(name)) > 0),
  description          text,
  definition           jsonb NOT NULL DEFAULT '{}',
  status               public.workflow_status NOT NULL DEFAULT 'draft',
  version              integer NOT NULL DEFAULT 1,
  execution_mode       text NOT NULL DEFAULT 'n8n' CHECK (execution_mode IN ('n8n', 'builtin')),
  config               jsonb NOT NULL DEFAULT '{}',
  created_by_user_id   uuid NOT NULL REFERENCES public.users (id) ON DELETE RESTRICT,
  created_at           timestamptz NOT NULL DEFAULT now(),
  updated_at           timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_workflows_org_status ON public.workflows (organization_id, status);
CREATE INDEX idx_workflows_org_created ON public.workflows (organization_id, created_at DESC);

CREATE TRIGGER trg_workflows_updated_at
  BEFORE UPDATE ON public.workflows
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.workflows ENABLE ROW LEVEL SECURITY;

-- workflow_triggers: how workflows are triggered
CREATE TABLE IF NOT EXISTS public.workflow_triggers (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id      uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  workflow_id          uuid NOT NULL REFERENCES public.workflows (id) ON DELETE CASCADE,
  name                 text NOT NULL CHECK (length(btrim(name)) > 0),
  trigger_type         public.workflow_trigger_type NOT NULL,
  event_type           text,
  schedule_cron        text,
  config               jsonb NOT NULL DEFAULT '{}',
  enabled              boolean NOT NULL DEFAULT true,
  created_at           timestamptz NOT NULL DEFAULT now(),
  updated_at           timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_workflow_triggers_org_workflow ON public.workflow_triggers (organization_id, workflow_id);
CREATE INDEX idx_workflow_triggers_event_type ON public.workflow_triggers (event_type) WHERE event_type IS NOT NULL;

CREATE TRIGGER trg_workflow_triggers_updated_at
  BEFORE UPDATE ON public.workflow_triggers
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.workflow_triggers ENABLE ROW LEVEL SECURITY;

-- workflow_executions: execution queue + history with retry tracking
CREATE TABLE IF NOT EXISTS public.workflow_executions (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id      uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  workflow_id          uuid NOT NULL REFERENCES public.workflows (id) ON DELETE CASCADE,
  trigger_id           uuid REFERENCES public.workflow_triggers (id) ON DELETE SET NULL,
  status               public.execution_status NOT NULL DEFAULT 'queued',
  input                jsonb NOT NULL DEFAULT '{}',
  output               jsonb,
  error                jsonb,
  started_at           timestamptz,
  finished_at          timestamptz,
  attempts             integer NOT NULL DEFAULT 0,
  max_attempts         integer NOT NULL DEFAULT 3,
  retry_delay_seconds  integer NOT NULL DEFAULT 60,
  retry_backoff        text NOT NULL DEFAULT 'exponential' CHECK (retry_backoff IN ('constant', 'exponential')),
  next_retry_at        timestamptz,
  requested_by_user_id uuid REFERENCES public.users (id) ON DELETE SET NULL,
  trace_id             uuid,
  created_at           timestamptz NOT NULL DEFAULT now(),
  updated_at           timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_workflow_executions_org_status ON public.workflow_executions (organization_id, status);
CREATE INDEX idx_workflow_executions_org_workflow ON public.workflow_executions (organization_id, workflow_id);
CREATE INDEX idx_workflow_executions_next_retry ON public.workflow_executions (next_retry_at) WHERE status = 'retrying';
CREATE INDEX idx_workflow_executions_trace_id ON public.workflow_executions (trace_id) WHERE trace_id IS NOT NULL;

CREATE TRIGGER trg_workflow_executions_updated_at
  BEFORE UPDATE ON public.workflow_executions
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.workflow_executions ENABLE ROW LEVEL SECURITY;

-- workflow_events: append-only event log for trigger matching
CREATE TABLE IF NOT EXISTS public.workflow_events (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id      uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  event_type           text NOT NULL CHECK (length(btrim(event_type)) > 0),
  payload              jsonb NOT NULL DEFAULT '{}',
  consumed             boolean NOT NULL DEFAULT false,
  consumed_at          timestamptz,
  occurred_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_workflow_events_org_type ON public.workflow_events (organization_id, event_type);
CREATE INDEX idx_workflow_events_org_consumed ON public.workflow_events (organization_id, consumed) WHERE NOT consumed;
CREATE INDEX idx_workflow_events_occurred ON public.workflow_events (occurred_at DESC);

ALTER TABLE public.workflow_events ENABLE ROW LEVEL SECURITY;

-- credentials: encrypted credential storage for integrations
CREATE TABLE IF NOT EXISTS public.credentials (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id      uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  name                 text NOT NULL CHECK (length(btrim(name)) > 0),
  credential_type      public.credential_type NOT NULL,
  encrypted_value      text NOT NULL,
  value_preview        text NOT NULL,
  description          text,
  expires_at           timestamptz,
  created_by_user_id   uuid NOT NULL REFERENCES public.users (id) ON DELETE RESTRICT,
  last_used_at         timestamptz,
  created_at           timestamptz NOT NULL DEFAULT now(),
  updated_at           timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_credentials_org_type ON public.credentials (organization_id, credential_type);
CREATE UNIQUE INDEX uq_credentials_org_name ON public.credentials (organization_id, name);

CREATE TRIGGER trg_credentials_updated_at
  BEFORE UPDATE ON public.credentials
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.credentials ENABLE ROW LEVEL SECURITY;