-- business_insights: generated business insight rows (Phase 5D)
CREATE TABLE IF NOT EXISTS public.business_insights (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  insight_type    public.insight_type NOT NULL,
  severity        public.insight_severity NOT NULL DEFAULT 'info',
  status          public.insight_status NOT NULL DEFAULT 'active',
  title           text NOT NULL,
  summary         text NOT NULL,
  source_table    text,
  source_row_id   uuid,
  metadata        jsonb NOT NULL DEFAULT '{}',
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT chk_business_insights_title_not_blank CHECK (length(btrim(title)) > 0),
  CONSTRAINT chk_business_insights_summary_not_blank CHECK (length(btrim(summary)) > 0),
  CONSTRAINT chk_business_insights_source_table_not_blank CHECK (
    source_table IS NULL OR length(btrim(source_table)) > 0
  )
);

CREATE INDEX IF NOT EXISTS idx_business_insights_org_status
  ON public.business_insights (organization_id, status);
CREATE INDEX IF NOT EXISTS idx_business_insights_org_type
  ON public.business_insights (organization_id, insight_type);
CREATE INDEX IF NOT EXISTS idx_business_insights_org_created
  ON public.business_insights (organization_id, created_at DESC);
-- Polymorphic source lookup.
CREATE INDEX IF NOT EXISTS idx_business_insights_source
  ON public.business_insights (source_table, source_row_id)
  WHERE source_row_id IS NOT NULL;

DROP TRIGGER IF EXISTS trg_business_insights_updated_at ON public.business_insights;
CREATE TRIGGER trg_business_insights_updated_at
  BEFORE UPDATE ON public.business_insights
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.business_insights ENABLE ROW LEVEL SECURITY;
