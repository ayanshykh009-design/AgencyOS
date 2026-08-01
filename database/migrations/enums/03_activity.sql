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
  'lead_lost'
);
