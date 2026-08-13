-- growth_analyses: deterministic analysis snapshots (M7 Growth Intelligence)
CREATE TYPE public.growth_analysis_type AS ENUM (
  'health', 'kpis', 'pipeline', 'funnel', 'conversion',
  'revenue', 'activity', 'bottlenecks', 'opportunities', 'trends'
);

CREATE TYPE public.growth_analysis_status AS ENUM (
  'completed', 'failed'
);

CREATE TABLE IF NOT EXISTS public.growth_analyses (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id   uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  analysis_type     public.growth_analysis_type NOT NULL,
  status            public.growth_analysis_status NOT NULL DEFAULT 'completed',
  period_start      timestamptz NOT NULL,
  period_end        timestamptz NOT NULL,
  health_score      numeric(5, 2),
  summary           text NOT NULL,
  details           jsonb NOT NULL DEFAULT '{}',
  evidence          jsonb NOT NULL DEFAULT '[]',
  weights           jsonb NOT NULL DEFAULT '{}',
  metrics_used      jsonb NOT NULL DEFAULT '[]',
  error             text,
  generated_by      text NOT NULL DEFAULT 'agent',
  generated_at      timestamptz NOT NULL DEFAULT now(),
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT chk_growth_analyses_summary_not_blank CHECK (length(btrim(summary)) > 0),
  CONSTRAINT chk_growth_analyses_period_order CHECK (period_end >= period_start),
  CONSTRAINT chk_growth_analyses_health_range CHECK (
    health_score IS NULL OR (health_score >= 0 AND health_score <= 100)
  ),
  CONSTRAINT chk_growth_analyses_generated_by_not_blank CHECK (length(btrim(generated_by)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_growth_analyses_org_created
  ON public.growth_analyses (organization_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_growth_analyses_org_type_created
  ON public.growth_analyses (organization_id, analysis_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_growth_analyses_org_status_created
  ON public.growth_analyses (organization_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_growth_analyses_org_period
  ON public.growth_analyses (organization_id, period_start, period_end);

DROP TRIGGER IF EXISTS trg_growth_analyses_updated_at ON public.growth_analyses;
CREATE TRIGGER trg_growth_analyses_updated_at
  BEFORE UPDATE ON public.growth_analyses
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.growth_analyses ENABLE ROW LEVEL SECURITY;
