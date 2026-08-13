-- =====================================================================
-- 0023_m7_growth_forecasts_extended.sql
-- Phase M7: Growth Intelligence — forecast engine columns.
--
-- Extends the M2 growth_forecasts table (additive only) with the columns the
-- deterministic forecast engines need:
--
--   * method               engine key (linear_trend / moving_average /
--                          pipeline_weighted / seasonal_naive)
--   * base_period_start/end the history window the forecast was fit on
--   * point_estimate       central projection (mirrors total_value)
--   * lower_bound/upper_bound deterministic interval (mirrors confidence_*)
--   * series               projected per-period points [{period, value, low, high}]
--   * errors               per-period residuals / fit diagnostics {mae, mape, ...}
--
-- Existing rows are backfilled so old snapshots stay consistent
-- (point_estimate := total_value, bounds := confidence_low/high).
-- =====================================================================

-- ---------------------------------------------------------------------
-- Columns (idempotent: ADD COLUMN IF NOT EXISTS).
-- ---------------------------------------------------------------------
ALTER TABLE public.growth_forecasts
  ADD COLUMN IF NOT EXISTS method            text;

ALTER TABLE public.growth_forecasts
  ADD COLUMN IF NOT EXISTS base_period_start timestamptz;

ALTER TABLE public.growth_forecasts
  ADD COLUMN IF NOT EXISTS base_period_end   timestamptz;

ALTER TABLE public.growth_forecasts
  ADD COLUMN IF NOT EXISTS point_estimate    numeric(18, 6);

ALTER TABLE public.growth_forecasts
  ADD COLUMN IF NOT EXISTS lower_bound       numeric(18, 6);

ALTER TABLE public.growth_forecasts
  ADD COLUMN IF NOT EXISTS upper_bound       numeric(18, 6);

ALTER TABLE public.growth_forecasts
  ADD COLUMN IF NOT EXISTS series            jsonb NOT NULL DEFAULT '[]';

ALTER TABLE public.growth_forecasts
  ADD COLUMN IF NOT EXISTS errors            jsonb NOT NULL DEFAULT '{}';

-- ---------------------------------------------------------------------
-- Backfill legacy rows (idempotent by construction; harmless on re-run).
-- ---------------------------------------------------------------------
UPDATE public.growth_forecasts
SET point_estimate = COALESCE(point_estimate, total_value),
    lower_bound    = COALESCE(lower_bound, confidence_low),
    upper_bound    = COALESCE(upper_bound, confidence_high)
WHERE point_estimate IS NULL;

-- ---------------------------------------------------------------------
-- Constraints (PostgreSQL has no ADD CONSTRAINT IF NOT EXISTS; guard).
-- ---------------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.growth_forecasts'::regclass
      AND conname = 'chk_growth_forecasts_method_not_blank'
  ) THEN
    ALTER TABLE public.growth_forecasts
      ADD CONSTRAINT chk_growth_forecasts_method_not_blank
      CHECK (method IS NULL OR length(btrim(method)) > 0);
  END IF;
END;
$$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.growth_forecasts'::regclass
      AND conname = 'chk_growth_forecasts_base_period_order'
  ) THEN
    ALTER TABLE public.growth_forecasts
      ADD CONSTRAINT chk_growth_forecasts_base_period_order
      CHECK (base_period_start IS NULL OR base_period_end IS NULL OR base_period_end >= base_period_start);
  END IF;
END;
$$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.growth_forecasts'::regclass
      AND conname = 'chk_growth_forecasts_bounds_order'
  ) THEN
    ALTER TABLE public.growth_forecasts
      ADD CONSTRAINT chk_growth_forecasts_bounds_order
      CHECK (
        lower_bound IS NULL OR point_estimate IS NULL OR upper_bound IS NULL
        OR (lower_bound <= point_estimate AND point_estimate <= upper_bound)
      );
  END IF;
END;
$$;

-- =====================================================================
-- ROLLBACK
-- =====================================================================
-- ALTER TABLE public.growth_forecasts DROP CONSTRAINT IF EXISTS chk_growth_forecasts_bounds_order;
-- ALTER TABLE public.growth_forecasts DROP CONSTRAINT IF EXISTS chk_growth_forecasts_base_period_order;
-- ALTER TABLE public.growth_forecasts DROP CONSTRAINT IF EXISTS chk_growth_forecasts_method_not_blank;
-- ALTER TABLE public.growth_forecasts DROP COLUMN IF EXISTS errors;
-- ALTER TABLE public.growth_forecasts DROP COLUMN IF EXISTS series;
-- ALTER TABLE public.growth_forecasts DROP COLUMN IF EXISTS upper_bound;
-- ALTER TABLE public.growth_forecasts DROP COLUMN IF EXISTS lower_bound;
-- ALTER TABLE public.growth_forecasts DROP COLUMN IF EXISTS point_estimate;
-- ALTER TABLE public.growth_forecasts DROP COLUMN IF EXISTS base_period_end;
-- ALTER TABLE public.growth_forecasts DROP COLUMN IF EXISTS base_period_start;
-- ALTER TABLE public.growth_forecasts DROP COLUMN IF EXISTS method;
-- =====================================================================
