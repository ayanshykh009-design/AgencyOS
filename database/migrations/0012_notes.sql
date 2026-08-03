-- =====================================================================
-- 0012_notes.sql
-- Notes: free-form commentary attached to a lead.
--
--   * notes: org-scoped, always lead-scoped (lead_id NOT NULL), authored
--     by a team member, with an optional pinned flag for highlighting.
--   * activity_event_type grows note_created/updated/deleted so note
--     timelines are auditable via activity_logs.
--
-- All statements are idempotent so CI can re-apply them against a live
-- database.
-- =====================================================================

-- ---------------------------------------------------------------------
-- extend the closed activity event set with note lifecycle events
-- ---------------------------------------------------------------------
DO $$
DECLARE
  v_label text;
BEGIN
  FOREACH v_label IN ARRAY ARRAY['note_created', 'note_updated', 'note_deleted']
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
-- notes
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.notes (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id      uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  lead_id              uuid NOT NULL REFERENCES public.leads (id) ON DELETE CASCADE,
  author_user_id       uuid REFERENCES public.users (id) ON DELETE SET NULL,
  body                 text NOT NULL CHECK (length(btrim(body)) > 0),
  pinned               boolean NOT NULL DEFAULT false,
  created_at           timestamptz NOT NULL DEFAULT now(),
  updated_at           timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_notes_org_lead ON public.notes (organization_id, lead_id, created_at DESC);

CREATE TRIGGER trg_notes_updated_at
  BEFORE UPDATE ON public.notes
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.notes ENABLE ROW LEVEL SECURITY;

-- =====================================================================
-- ROLLBACK
-- =====================================================================
-- DROP TABLE IF EXISTS public.notes;
-- ALTER TYPE public.activity_event_type DROP VALUE IF EXISTS 'note_deleted';
-- ALTER TYPE public.activity_event_type DROP VALUE IF EXISTS 'note_updated';
-- ALTER TYPE public.activity_event_type DROP VALUE IF EXISTS 'note_created';
-- =====================================================================
