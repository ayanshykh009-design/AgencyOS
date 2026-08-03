-- activity_event_type: the closed set of business events recorded in
-- activity_logs.
CREATE TYPE public.activity_event_type AS ENUM (
  'lead_imported',
  'research_completed',
  'score_generated',
  'email_sent',
  'whatsapp_sent',
  'manual_message_completed',
  'reply_received',
  'meeting_booked',
  'proposal_sent',
  'lead_won',
  'lead_lost',
  'user_invited',
  'invite_accepted',
  'invite_revoked',
  'user_role_changed',
  'user_status_changed',
  'lead_assigned',
  'task_created',
  'task_updated',
  'task_completed',
  'task_deleted',
  'note_created',
  'note_updated',
  'note_deleted'
);
