-- growth_forecasts: deterministic growth forecasts (Phase 5D / M7 extended)
CREATE TABLE IF NOT EXISTS public.growth_forecasts (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  forecast_type   text NOT NULL,
  horizon_start   timestamptz NOT NULL,
  horizon_end     timestamptz NOT NULL,
  total_value     numeric(18, 6) NOT NULL,
  confidence_low  numeric(18, 6),
  confidence_high numeric(18, 6),
  model_config    jsonb NOT NULL DEFAULT '{}',
  method          text,
  base_period_start timestamptz,
  base_period_end   timestamptz,
  point_estimate  numeric(18, 6),
  lower_bound     numeric(18, 6),
  upper_bound     numeric(18, 6),
  series          jsonb NOT NULL DEFAULT '[]',
  errors          jsonb NOT NULL DEFAULT '{}',
  generated_at    timestamptz NOT NULL DEFAULT now(),
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT chk_growth_forecasts_type_not_blank CHECK (length(btrim(forecast_type)) > 0),
  CONSTRAINT chk_growth_forecasts_total_nonneg CHECK (total_value >= 0),
  CONSTRAINT chk_growth_forecasts_horizon_order CHECK (horizon_end >= horizon_start),
  CONSTRAINT chk_growth_forecasts_confidence_order CHECK (
    confidence_low IS NULL OR confidence_high IS NULL OR confidence_low <= confidence_high
  ),
  CONSTRAINT chk_growth_forecasts_method_not_blank CHECK (
    method IS NULL OR length(btrim(method)) > 0
  ),
  CONSTRAINT chk_growth_forecasts_base_period_order CHECK (
    base_period_start IS NULL OR base_period_end IS NULL OR base_period_end >= base_period_start
  ),
  CONSTRAINT chk_growth_forecasts_bounds_order CHECK (
    lower_bound IS NULL OR point_estimate IS NULL OR upper_bound IS NULL
    OR (lower_bound <= point_estimate AND point_estimate <= upper_bound)
  )
);

-- Latest-by-type and org-wide history listings.
CREATE INDEX IF NOT EXISTS idx_growth_forecasts_org_type_horizon
  ON public.growth_forecasts (organization_id, forecast_type, horizon_start DESC);
CREATE INDEX IF NOT EXISTS idx_growth_forecasts_org_created
  ON public.growth_forecasts (organization_id, created_at DESC);

DROP TRIGGER IF EXISTS trg_growth_forecasts_updated_at ON public.growth_forecasts;
CREATE TRIGGER trg_growth_forecasts_updated_at
  BEFORE UPDATE ON public.growth_forecasts
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.growth_forecasts ENABLE ROW LEVEL SECURITY;
