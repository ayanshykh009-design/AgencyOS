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
  'note_created', 'note_updated', 'note_deleted'
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
