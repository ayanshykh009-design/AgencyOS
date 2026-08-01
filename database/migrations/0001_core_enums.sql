-- =====================================================================
-- 0001_core_enums.sql
-- Centralized enum type definitions for AgencyOS.
-- Canonical reference: database/migrations/enums/ (keep in sync).
-- =====================================================================

-- Idempotent helper: create a public enum type if it does not exist.
-- Dropped at the end of this migration (enum creation only).
CREATE OR REPLACE FUNCTION public.agencyos_create_enum(p_name text, p_values text[])
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
  v_expr text;
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'public' AND t.typname = p_name
  ) THEN
    SELECT string_agg(quote_literal(v), ', ' ORDER BY ord)
      INTO v_expr
      FROM unnest(p_values) WITH ORDINALITY AS x(v, ord);
    EXECUTE format('CREATE TYPE public.%I AS ENUM (%s)', p_name, v_expr);
  END IF;
END;
$$;

-- Identity
SELECT public.agencyos_create_enum('user_role', ARRAY['owner', 'admin', 'member', 'viewer']);

-- Lead lifecycle
SELECT public.agencyos_create_enum(
  'lead_status',
  ARRAY['new', 'researching', 'contacted', 'meeting_booked', 'proposal_sent', 'won', 'lost']
);

-- Outreach channels and message lifecycle
SELECT public.agencyos_create_enum(
  'outreach_channel',
  ARRAY['email', 'whatsapp', 'contact_form', 'linkedin', 'instagram', 'facebook']
);
SELECT public.agencyos_create_enum(
  'outreach_status',
  ARRAY['queued', 'sending', 'sent', 'delivered', 'failed', 'skipped', 'manually_sent', 'replied']
);

-- CSV import lifecycle
SELECT public.agencyos_create_enum(
  'import_status',
  ARRAY['pending', 'processing', 'completed', 'failed', 'cancelled']
);

-- Business activity events
SELECT public.agencyos_create_enum(
  'activity_event_type',
  ARRAY[
    'lead_imported', 'research_completed', 'score_generated', 'email_sent',
    'whatsapp_sent', 'manual_message_completed', 'reply_received', 'meeting_booked',
    'proposal_sent', 'lead_won', 'lead_lost'
  ]
);

-- Conversation authorship
SELECT public.agencyos_create_enum(
  'conversation_sender',
  ARRAY['lead', 'agent', 'system']
);

DROP FUNCTION public.agencyos_create_enum(text, text[]);

-- =====================================================================
-- ROLLBACK
-- =====================================================================
-- DROP TYPE IF EXISTS public.conversation_sender;
-- DROP TYPE IF EXISTS public.activity_event_type;
-- DROP TYPE IF EXISTS public.import_status;
-- DROP TYPE IF EXISTS public.outreach_status;
-- DROP TYPE IF EXISTS public.outreach_channel;
-- DROP TYPE IF EXISTS public.lead_status;
-- DROP TYPE IF EXISTS public.user_role;
-- =====================================================================
