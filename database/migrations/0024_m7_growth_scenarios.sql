-- =====================================================================
-- 0024_m7_growth_scenarios.sql
-- Phase M7: Growth Intelligence — deterministic scenario analysis.
--
--   * growth_scenarios — saved "what-if" projections. Each row stores the
--                        assumption deltas applied to a forecast (or to the
--                        live pipeline when forecast_id is NULL) and the
--                        resulting projected values.
--
-- Backward compatibility:
--   * additive only (new table; nothing existing is touched)
--   * CREATE TABLE / INDEX / TRIGGER IF NOT EXISTS are idempotent
--   * safe to run multiple times; zero data loss
-- =====================================================================

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

-- Tenant-scoped listing (newest first).
CREATE INDEX IF NOT EXISTS idx_growth_scenarios_org_created
  ON public.growth_scenarios (organization_id, created_at DESC);
-- Scenarios anchored to one forecast.
CREATE INDEX IF NOT EXISTS idx_growth_scenarios_forecast
  ON public.growth_scenarios (forecast_id);
-- Case-insensitive uniqueness per organization.
CREATE UNIQUE INDEX IF NOT EXISTS uq_growth_scenarios_org_name
  ON public.growth_scenarios (organization_id, lower(name));

DROP TRIGGER IF EXISTS trg_growth_scenarios_updated_at ON public.growth_scenarios;

CREATE TRIGGER trg_growth_scenarios_updated_at
  BEFORE UPDATE ON public.growth_scenarios
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.growth_scenarios ENABLE ROW LEVEL SECURITY;

-- =====================================================================
-- ROLLBACK
-- =====================================================================
-- DROP INDEX IF EXISTS public.uq_growth_scenarios_org_name;
-- DROP INDEX IF EXISTS public.idx_growth_scenarios_forecast;
-- DROP INDEX IF EXISTS public.idx_growth_scenarios_org_created;
-- DROP TABLE IF EXISTS public.growth_scenarios;
-- =====================================================================
