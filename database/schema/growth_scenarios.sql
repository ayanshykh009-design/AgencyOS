-- growth_scenarios: saved what-if projections (M7 Growth Intelligence)
CREATE TABLE IF NOT EXISTS public.growth_scenarios (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id    uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  forecast_id        uuid REFERENCES public.growth_forecasts (id) ON DELETE CASCADE,
  name               text NOT NULL,
  description        text,
  assumption_deltas  jsonb NOT NULL DEFAULT '{}',
  result             jsonb NOT NULL DEFAULT '{}',
  created_by_user_id uuid REFERENCES public.users (id) ON DELETE SET NULL,
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT chk_growth_scenarios_name_not_blank CHECK (length(btrim(name)) > 0),
  CONSTRAINT chk_growth_scenarios_assumptions_object CHECK (jsonb_typeof(assumption_deltas) = 'object'),
  CONSTRAINT chk_growth_scenarios_result_object CHECK (jsonb_typeof(result) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_growth_scenarios_org_created
  ON public.growth_scenarios (organization_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_growth_scenarios_forecast
  ON public.growth_scenarios (forecast_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_growth_scenarios_org_name
  ON public.growth_scenarios (organization_id, lower(name));

DROP TRIGGER IF EXISTS trg_growth_scenarios_updated_at ON public.growth_scenarios;
CREATE TRIGGER trg_growth_scenarios_updated_at
  BEFORE UPDATE ON public.growth_scenarios
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.growth_scenarios ENABLE ROW LEVEL SECURITY;
