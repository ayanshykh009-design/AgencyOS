-- growth_recommendations: evidence-backed recommendations (M7)
CREATE TYPE public.recommendation_priority AS ENUM (
  'high', 'medium', 'low'
);

CREATE TYPE public.recommendation_status AS ENUM (
  'active', 'acknowledged', 'applied', 'dismissed'
);

CREATE TABLE IF NOT EXISTS public.growth_recommendations (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id     uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  recommendation_type text NOT NULL,
  priority            public.recommendation_priority NOT NULL DEFAULT 'medium',
  confidence          public.recommendation_priority NOT NULL DEFAULT 'medium',
  status              public.recommendation_status NOT NULL DEFAULT 'active',
  title               text NOT NULL,
  summary             text NOT NULL,
  rationale           text,
  action_type         text,
  action_payload      jsonb NOT NULL DEFAULT '{}',
  source_analysis_id  uuid REFERENCES public.growth_analyses (id) ON DELETE SET NULL,
  evidence            jsonb NOT NULL DEFAULT '[]',
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT chk_growth_recommendations_type_not_blank CHECK (length(btrim(recommendation_type)) > 0),
  CONSTRAINT chk_growth_recommendations_title_not_blank CHECK (length(btrim(title)) > 0),
  CONSTRAINT chk_growth_recommendations_summary_not_blank CHECK (length(btrim(summary)) > 0),
  CONSTRAINT chk_growth_recommendations_action_type_not_blank CHECK (
    action_type IS NULL OR length(btrim(action_type)) > 0
  )
);

CREATE INDEX IF NOT EXISTS idx_growth_recommendations_org_status
  ON public.growth_recommendations (organization_id, status);
CREATE INDEX IF NOT EXISTS idx_growth_recommendations_org_created
  ON public.growth_recommendations (organization_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_growth_recommendations_org_priority
  ON public.growth_recommendations (organization_id, priority);
CREATE INDEX IF NOT EXISTS idx_growth_recommendations_analysis
  ON public.growth_recommendations (source_analysis_id);

DROP TRIGGER IF EXISTS trg_growth_recommendations_updated_at ON public.growth_recommendations;
CREATE TRIGGER trg_growth_recommendations_updated_at
  BEFORE UPDATE ON public.growth_recommendations
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.growth_recommendations ENABLE ROW LEVEL SECURITY;
