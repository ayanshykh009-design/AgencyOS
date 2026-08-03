-- Notes: free-form commentary attached to a lead.
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

CREATE INDEX IF NOT EXISTS idx_notes_org_lead
  ON public.notes (organization_id, lead_id, created_at DESC);

DROP TRIGGER IF EXISTS trg_notes_updated_at ON public.notes;
CREATE TRIGGER trg_notes_updated_at
  BEFORE UPDATE ON public.notes
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
