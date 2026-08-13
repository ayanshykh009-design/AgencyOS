-- =====================================================================
-- 0022_m7_growth_analyses.sql
-- Phase M7: Growth Intelligence — analysis snapshots + health weights.
--
--   * growth_analysis_type / growth_analysis_status  — labels
--   * growth_analyses       — org-scoped analysis snapshots (deterministic)
--   * growth_health_weights — configurable, versioned business-health weights
--
-- Backward compatibility:
--   * additive only (new enum types + new tables; nothing existing is touched)
--   * CREATE TABLE / INDEX / TRIGGER IF NOT EXISTS are idempotent
--   * enum creation guarded by pg_type existence checks
--   * safe to run multiple times; zero data loss
-- =====================================================================

-- ---------------------------------------------------------------------
-- growth_analysis_type: what a growth_analyses row measures.
-- Each snapshot is produced by one deterministic analysis engine.
-- ---------------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'public' AND t.typname = 'growth_analysis_type'
  ) THEN
    CREATE TYPE public.growth_analysis_type AS ENUM (
      'health', 'kpis', 'pipeline', 'funnel', 'conversion',
      'revenue', 'activity', 'bottlenecks', 'opportunities', 'trends'
    );
  END IF;
END;
$$;

-- ---------------------------------------------------------------------
-- growth_analysis_status: lifecycle of an analysis snapshot.
--   completed  the snapshot was produced and persisted
--   failed     the engine errored; error holds the sanitized reason
-- ---------------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'public' AND t.typname = 'growth_analysis_status'
  ) THEN
    CREATE TYPE public.growth_analysis_status AS ENUM (
      'completed', 'failed'
    );
  END IF;
END;
$$;

-- ---------------------------------------------------------------------
-- growth_health_weights: configurable, versioned health-weight sets.
--
-- Business health is a weighted composite over deterministic KPI z-scores
-- and pipeline ratios. Weights are per-org and versioned so an admin can
-- retune the model without disturbing historical snapshots (each analysis
-- row copies the weights it was computed with). Exactly one version may be
-- active per org at a time (partial unique index); when no row exists the
-- service falls back to the built-in default weights.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.growth_health_weights (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id    uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  version            integer NOT NULL,
  weights            jsonb NOT NULL,
  is_active          boolean NOT NULL DEFAULT FALSE,
  created_by_user_id uuid REFERENCES public.users (id) ON DELETE SET NULL,
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT chk_growth_health_weights_version_positive CHECK (version > 0),
  CONSTRAINT chk_growth_health_weights_weights_object CHECK (jsonb_typeof(weights) = 'object')
);

-- One active weight set per organization.
CREATE UNIQUE INDEX IF NOT EXISTS uq_growth_health_weights_org_active
  ON public.growth_health_weights (organization_id)
  WHERE is_active;
-- Version listing (newest first) and activation lookups.
CREATE INDEX IF NOT EXISTS idx_growth_health_weights_org_version
  ON public.growth_health_weights (organization_id, version DESC);

CREATE TRIGGER trg_growth_health_weights_updated_at
  BEFORE UPDATE ON public.growth_health_weights
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.growth_health_weights ENABLE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------
-- growth_analyses: deterministic analysis snapshots (org-scoped).
--
-- One row per engine run. ``details`` carries the engine's structured
-- output; ``evidence`` lists the concrete data points each finding rests on
-- (metric values, z-scores, ratios) so recommendations stay traceable;
-- ``weights`` is the weight set the health score used ('' for non-health
-- analyses); ``metrics_used`` records the metric types consumed so the
-- frontend can explain coverage.
-- ---------------------------------------------------------------------
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

-- Tenant-scoped listings (newest first, optional type/status filters).
CREATE INDEX IF NOT EXISTS idx_growth_analyses_org_created
  ON public.growth_analyses (organization_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_growth_analyses_org_type_created
  ON public.growth_analyses (organization_id, analysis_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_growth_analyses_org_status_created
  ON public.growth_analyses (organization_id, status, created_at DESC);
-- Latest-within-window lookups (period filters on the dashboard).
CREATE INDEX IF NOT EXISTS idx_growth_analyses_org_period
  ON public.growth_analyses (organization_id, period_start, period_end);

CREATE TRIGGER trg_growth_analyses_updated_at
  BEFORE UPDATE ON public.growth_analyses
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.growth_analyses ENABLE ROW LEVEL SECURITY;

-- =====================================================================
-- ROLLBACK
-- =====================================================================
-- DROP INDEX IF EXISTS public.idx_growth_analyses_org_period;
-- DROP INDEX IF EXISTS public.idx_growth_analyses_org_status_created;
-- DROP INDEX IF EXISTS public.idx_growth_analyses_org_type_created;
-- DROP INDEX IF EXISTS public.idx_growth_analyses_org_created;
-- DROP TABLE IF EXISTS public.growth_analyses;
-- DROP INDEX IF EXISTS public.idx_growth_health_weights_org_version;
-- DROP INDEX IF EXISTS public.uq_growth_health_weights_org_active;
-- DROP TABLE IF EXISTS public.growth_health_weights;
-- DROP TYPE IF EXISTS public.growth_analysis_status;
-- DROP TYPE IF EXISTS public.growth_analysis_type;
-- =====================================================================
