-- Phase 5D: AI intelligence layer enum types.
-- Canonical reference: ../migrations/enums/ (the migration materializes them).
CREATE TYPE public.memory_type AS ENUM ('working', 'long_term');

CREATE TYPE public.memory_scope AS ENUM (
  'conversation', 'research', 'workflow', 'shared_context', 'knowledge', 'manual'
);

CREATE TYPE public.agent_run_status AS ENUM (
  'queued', 'running', 'succeeded', 'failed', 'cancelled'
);

CREATE TYPE public.agent_run_trigger AS ENUM (
  'manual', 'schedule', 'workflow', 'event'
);

CREATE TYPE public.agent_state_status AS ENUM (
  'active', 'paused', 'degraded', 'disabled'
);

CREATE TYPE public.agent_health AS ENUM ('healthy', 'degraded', 'unhealthy');

CREATE TYPE public.notification_type AS ENUM (
  'approval_request', 'approval_result', 'workflow_event',
  'agent_event', 'system', 'briefing', 'insight'
);

CREATE TYPE public.approval_request_status AS ENUM (
  'pending', 'approved', 'denied', 'expired', 'cancelled'
);

CREATE TYPE public.approval_log_action AS ENUM (
  'requested', 'notified', 'approved', 'denied', 'expired', 'cancelled'
);

CREATE TYPE public.briefing_type AS ENUM ('daily', 'weekly', 'manual');

CREATE TYPE public.insight_type AS ENUM (
  'opportunity', 'risk', 'trend', 'anomaly', 'recommendation'
);

CREATE TYPE public.insight_severity AS ENUM (
  'info', 'low', 'medium', 'high', 'critical'
);

CREATE TYPE public.insight_status AS ENUM ('active', 'acknowledged', 'dismissed');
