-- =====================================================================
-- 0013_automation.sql
-- Automation Foundation: workflows, triggers, executions, events, credentials.
--
--   * workflow_status / workflow_trigger_type / execution_status /
--     credential_type enums (values match database/schema/00_enums.sql;
--     created here so the migration is self-contained like its siblings)
--   * workflows: tenant-scoped workflow registry with execution config
--   * workflow_triggers: how workflows are triggered (manual/event/schedule)
--   * workflow_executions: execution queue + history with retry tracking
--   * workflow_events: append-only event log for trigger matching
--   * credentials: encrypted credential storage for integrations
--   * activity_event_type extended with automation events
--
-- All statements are idempotent so CI can re-apply them against a live database.
-- =====================================================================

-- ---------------------------------------------------------------------
-- automation enum types (guarded by pg_type existence checks)
-- ---------------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'public' AND t.typname = 'workflow_status'
  ) THEN
    CREATE TYPE public.workflow_status AS ENUM (
      'draft', 'active', 'paused', 'archived'
    );
  END IF;
END;
$$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'public' AND t.typname = 'workflow_trigger_type'
  ) THEN
    CREATE TYPE public.workflow_trigger_type AS ENUM (
      'manual', 'event', 'schedule'
    );
  END IF;
END;
$$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'public' AND t.typname = 'execution_status'
  ) THEN
    CREATE TYPE public.execution_status AS ENUM (
      'queued', 'running', 'succeeded', 'failed', 'retrying',
      'cancelled', 'timed_out'
    );
  END IF;
END;
$$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'public' AND t.typname = 'credential_type'
  ) THEN
    CREATE TYPE public.credential_type AS ENUM (
      'n8n_api_key', 'api_key', 'basic_auth'
    );
  END IF;
END;
$$;

-- ---------------------------------------------------------------------
-- extend activity_event_type with automation lifecycle events
-- ---------------------------------------------------------------------
DO $$
DECLARE
  v_label text;
BEGIN
  FOREACH v_label IN ARRAY ARRAY[
    'workflow_created', 'workflow_updated', 'workflow_activated',
    'workflow_paused', 'workflow_archived', 'workflow_deleted',
    'execution_queued', 'execution_started', 'execution_completed',
    'execution_failed', 'execution_retried', 'execution_cancelled',
    'credential_created', 'credential_updated', 'credential_deleted',
    'trigger_created', 'trigger_updated', 'trigger_deleted'
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
-- workflows
-- ---------------------------------------------------------------------
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

-- ---------------------------------------------------------------------
-- workflow_triggers
-- ---------------------------------------------------------------------
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

-- ---------------------------------------------------------------------
-- workflow_executions
-- ---------------------------------------------------------------------
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

-- ---------------------------------------------------------------------
-- workflow_events
-- ---------------------------------------------------------------------
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

-- ---------------------------------------------------------------------
-- credentials
-- ---------------------------------------------------------------------
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

-- =====================================================================
-- ROLLBACK
-- =====================================================================
-- DROP TABLE IF EXISTS public.credentials;
-- DROP TABLE IF EXISTS public.workflow_events;
-- DROP TABLE IF EXISTS public.workflow_executions;
-- DROP TABLE IF EXISTS public.workflow_triggers;
-- DROP TABLE IF EXISTS public.workflows;
-- ALTER TYPE public.activity_event_type DROP VALUE IF EXISTS 'trigger_deleted';
-- ALTER TYPE public.activity_event_type DROP VALUE IF EXISTS 'trigger_updated';
-- ALTER TYPE public.activity_event_type DROP VALUE IF EXISTS 'trigger_created';
-- ALTER TYPE public.activity_event_type DROP VALUE IF EXISTS 'credential_deleted';
-- ALTER TYPE public.activity_event_type DROP VALUE IF EXISTS 'credential_updated';
-- ALTER TYPE public.activity_event_type DROP VALUE IF EXISTS 'credential_created';
-- ALTER TYPE public.activity_event_type DROP VALUE IF EXISTS 'execution_cancelled';
-- ALTER TYPE public.activity_event_type DROP VALUE IF EXISTS 'execution_retried';
-- ALTER TYPE public.activity_event_type DROP VALUE IF EXISTS 'execution_failed';
-- ALTER TYPE public.activity_event_type DROP VALUE IF EXISTS 'execution_completed';
-- ALTER TYPE public.activity_event_type DROP VALUE IF EXISTS 'execution_started';
-- ALTER TYPE public.activity_event_type DROP VALUE IF EXISTS 'execution_queued';
-- ALTER TYPE public.activity_event_type DROP VALUE IF EXISTS 'workflow_deleted';
-- ALTER TYPE public.activity_event_type DROP VALUE IF EXISTS 'workflow_archived';
-- ALTER TYPE public.activity_event_type DROP VALUE IF EXISTS 'workflow_paused';
-- ALTER TYPE public.activity_event_type DROP VALUE IF EXISTS 'workflow_activated';
-- ALTER TYPE public.activity_event_type DROP VALUE IF EXISTS 'workflow_updated';
-- ALTER TYPE public.activity_event_type DROP VALUE IF EXISTS 'workflow_created';
-- DROP TYPE IF EXISTS public.credential_type;
-- DROP TYPE IF EXISTS public.execution_status;
-- DROP TYPE IF EXISTS public.workflow_trigger_type;
-- DROP TYPE IF EXISTS public.workflow_status;
-- =====================================================================