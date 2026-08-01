-- Enum types used across the schema.
-- Canonical reference: ../migrations/enums/ (the migration materializes them).

CREATE TYPE public.user_role AS ENUM ('owner', 'admin', 'member', 'viewer');

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
  'proposal_sent', 'lead_won', 'lead_lost'
);

CREATE TYPE public.conversation_sender AS ENUM ('lead', 'agent', 'system');
