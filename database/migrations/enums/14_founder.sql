CREATE TYPE public.founder_message_sender AS ENUM ('user', 'assistant');

CREATE TYPE public.founder_proposal_status AS ENUM (
  'proposed', 'approved', 'denied', 'expired', 'cancelled', 'executing', 'succeeded', 'failed'
);

CREATE TYPE public.founder_action_type AS ENUM (
  'create_task', 'draft_email', 'send_email', 'run_workflow', 'export', 'general'
);
