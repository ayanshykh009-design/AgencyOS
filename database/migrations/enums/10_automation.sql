-- workflow_status: lifecycle of a workflow definition.
CREATE TYPE public.workflow_status AS ENUM (
  'draft',
  'active',
  'paused',
  'archived'
);

-- workflow_trigger_type: how a workflow is triggered.
CREATE TYPE public.workflow_trigger_type AS ENUM (
  'manual',
  'event',
  'schedule'
);

-- execution_status: lifecycle of a workflow execution.
CREATE TYPE public.execution_status AS ENUM (
  'queued',
  'running',
  'succeeded',
  'failed',
  'retrying',
  'cancelled',
  'timed_out'
);

-- credential_type: type of stored credential.
CREATE TYPE public.credential_type AS ENUM (
  'n8n_api_key',
  'api_key',
  'basic_auth'
);