-- Enum types used across the schema.
-- Canonical reference: ../migrations/enums/ (the migration materializes them).

CREATE TYPE public.user_role AS ENUM (
  'owner', 'admin', 'manager', 'member', 'sales_agent', 'viewer'
);

CREATE TYPE public.invite_status AS ENUM ('pending', 'accepted', 'revoked', 'expired');

CREATE TYPE public.lead_status AS ENUM (
  'new', 'researching', 'contacted', 'meeting_booked', 'proposal_sent', 'won', 'lost'
);

CREATE TYPE public.outreach_channel AS ENUM (
  'email', 'whatsapp', 'contact_form', 'linkedin', 'instagram', 'facebook'
);

CREATE TYPE public.outreach_status AS ENUM (
  'queued', 'sending', 'sent', 'delivered', 'failed', 'skipped',
  'manually_sent', 'replied'
);

CREATE TYPE public.import_status AS ENUM ('pending', 'processing', 'completed', 'failed', 'cancelled');

CREATE TYPE public.activity_event_type AS ENUM (
  'lead_imported', 'research_completed', 'score_generated', 'email_sent',
  'whatsapp_sent', 'manual_message_completed', 'reply_received', 'meeting_booked',
  'proposal_sent', 'lead_won', 'lead_lost', 'user_invited', 'invite_accepted',
  'invite_revoked', 'user_role_changed', 'user_status_changed', 'lead_assigned',
  'task_created', 'task_updated', 'task_completed', 'task_deleted',
  'note_created', 'note_updated', 'note_deleted',
  'workflow_created', 'workflow_updated', 'workflow_activated',
  'workflow_paused', 'workflow_archived', 'workflow_deleted',
  'execution_queued', 'execution_started', 'execution_completed',
  'execution_failed', 'execution_retried', 'execution_cancelled',
  'credential_created', 'credential_updated', 'credential_deleted',
  'trigger_created', 'trigger_updated', 'trigger_deleted',
  'automation_paused', 'automation_resumed'
);

CREATE TYPE public.conversation_sender AS ENUM ('lead', 'agent', 'system');

CREATE TYPE public.assignment_strategy AS ENUM ('manual', 'round_robin', 'rules');

CREATE TYPE public.assignment_method AS ENUM (
  'manual', 'round_robin', 'rules', 'bulk', 'unassigned'
);

CREATE TYPE public.stage_lifecycle AS ENUM ('open', 'won', 'lost');

CREATE TYPE public.task_status AS ENUM (
  'todo', 'in_progress', 'completed', 'cancelled'
);

CREATE TYPE public.task_priority AS ENUM ('low', 'medium', 'high', 'urgent');

CREATE TYPE public.recurrence_frequency AS ENUM ('daily', 'weekly', 'monthly');

CREATE TYPE public.workflow_status AS ENUM (
  'draft', 'active', 'paused', 'archived'
);

CREATE TYPE public.workflow_trigger_type AS ENUM (
  'manual', 'event', 'schedule'
);

CREATE TYPE public.execution_status AS ENUM (
  'queued', 'running', 'succeeded', 'failed', 'retrying', 'cancelled', 'timed_out'
);

CREATE TYPE public.credential_type AS ENUM (
  'n8n_api_key', 'api_key', 'basic_auth'
);

CREATE TYPE public.execution_event_type AS ENUM (
  'queued', 'started', 'adapter_dispatched', 'adapter_returned',
  'step_started', 'step_completed', 'step_failed',
  'retrying', 'succeeded', 'failed', 'cancelled', 'timed_out',
  'timeout_guard'
);

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

CREATE TYPE public.delivery_channel AS ENUM (
  'dashboard', 'email', 'whatsapp', 'push'
);

CREATE TYPE public.delivery_status AS ENUM (
  'queued', 'processing', 'delivered', 'retrying', 'failed', 'cancelled'
);

CREATE TYPE public.delivery_event_type AS ENUM (
  'queued', 'claimed', 'provider_dispatched', 'provider_returned',
  'delivered', 'retrying', 'failed', 'cancelled', 'timed_out',
  'recovery_guard', 'superseded'
);
