-- Where leads come from (channel + label), scoped per organization.
CREATE TABLE IF NOT EXISTS public.lead_sources (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  name            text NOT NULL CHECK (length(btrim(name)) > 0),
  channel         public.outreach_channel NOT NULL DEFAULT 'contact_form',
  description     text,
  is_active       boolean NOT NULL DEFAULT true,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_lead_sources_org_name UNIQUE (organization_id, name)
);

CREATE INDEX IF NOT EXISTS idx_lead_sources_org ON public.lead_sources (organization_id);

DROP TRIGGER IF EXISTS trg_lead_sources_updated_at ON public.lead_sources;
CREATE TRIGGER trg_lead_sources_updated_at
  BEFORE UPDATE ON public.lead_sources
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
