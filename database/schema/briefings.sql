-- briefings: generated founder briefings (Phase 5D)
CREATE TABLE IF NOT EXISTS public.briefings (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  briefing_type   public.briefing_type NOT NULL DEFAULT 'daily',
  title           text NOT NULL,
  summary         text NOT NULL,
  sections        jsonb NOT NULL DEFAULT '[]',
  metadata        jsonb NOT NULL DEFAULT '{}',
  generated_at    timestamptz NOT NULL DEFAULT now(),
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT chk_briefings_title_not_blank CHECK (length(btrim(title)) > 0),
  CONSTRAINT chk_briefings_summary_not_blank CHECK (length(btrim(summary)) > 0)
);

-- Latest-by-cadence and org-wide history listings.
CREATE INDEX IF NOT EXISTS idx_briefings_org_type_created
  ON public.briefings (organization_id, briefing_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_briefings_org_created
  ON public.briefings (organization_id, created_at DESC);

DROP TRIGGER IF EXISTS trg_briefings_updated_at ON public.briefings;
CREATE TRIGGER trg_briefings_updated_at
  BEFORE UPDATE ON public.briefings
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.briefings ENABLE ROW LEVEL SECURITY;
