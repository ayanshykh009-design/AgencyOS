-- growth_metrics: periodized growth/performance rows (Phase 5D)
CREATE TABLE IF NOT EXISTS public.growth_metrics (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  metric_type     text NOT NULL,
  period_start    timestamptz NOT NULL,
  period_end      timestamptz NOT NULL,
  value           numeric(18, 6) NOT NULL,
  unit            text,
  metadata        jsonb NOT NULL DEFAULT '{}',
  recorded_at     timestamptz NOT NULL DEFAULT now(),
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT chk_growth_metrics_type_not_blank CHECK (length(btrim(metric_type)) > 0),
  CONSTRAINT chk_growth_metrics_value_nonneg CHECK (value >= 0),
  CONSTRAINT chk_growth_metrics_period_order CHECK (period_end >= period_start)
);

-- Deterministic upsert target: one row per (org, metric_type, period).
CREATE UNIQUE INDEX IF NOT EXISTS uq_growth_metrics_org_type_period
  ON public.growth_metrics (organization_id, metric_type, period_start, period_end);
-- Series and retention queries.
CREATE INDEX IF NOT EXISTS idx_growth_metrics_org_type_recorded
  ON public.growth_metrics (organization_id, metric_type, recorded_at);
CREATE INDEX IF NOT EXISTS idx_growth_metrics_recorded_retention
  ON public.growth_metrics (recorded_at);

DROP TRIGGER IF EXISTS trg_growth_metrics_updated_at ON public.growth_metrics;
CREATE TRIGGER trg_growth_metrics_updated_at
  BEFORE UPDATE ON public.growth_metrics
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.growth_metrics ENABLE ROW LEVEL SECURITY;
