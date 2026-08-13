-- =====================================================================
-- 0025_m7_growth_recommendations.sql
-- Phase M7: Growth Intelligence — evidence-backed recommendations.
--
--   * recommendation_priority / recommendation_status — labels
--   * growth_recommendations — org-scoped, deterministic, evidence-linked
--                              recommendations produced by the growth agent.
--
-- Every recommendation carries ``evidence`` (the concrete data points it
-- rests on) and a qualitative ``confidence`` (high/medium/low). It links back
-- to the ``growth_analyses`` row that produced it when available, so the
-- frontend can trace reasoning.
--
-- Backward compatibility: additive only (new enum types + new table).
-- =====================================================================

-- ---------------------------------------------------------------------
-- recommendation_priority: actionable urgency of a recommendation.
-- ---------------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'public' AND t.typname = 'recommendation_priority'
  ) THEN
    CREATE TYPE public.recommendation_priority AS ENUM (
      'high', 'medium', 'low'
    );
  END IF;
END;
$$;

-- ---------------------------------------------------------------------
-- recommendation_status: triage lifecycle of a recommendation.
--   active -> acknowledged | applied
--   active -> dismissed
-- ---------------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'public' AND t.typname = 'recommendation_status'
  ) THEN
    CREATE TYPE public.recommendation_status AS ENUM (
      'active', 'acknowledged', 'applied', 'dismissed'
    );
  END IF;
END;
$$;

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

-- Tenant-scoped triage queues (active first, then by priority).
CREATE INDEX IF NOT EXISTS idx_growth_recommendations_org_status
  ON public.growth_recommendations (organization_id, status);
CREATE INDEX IF NOT EXISTS idx_growth_recommendations_org_created
  ON public.growth_recommendations (organization_id, created_at DESC);
-- Priority-ordered active list.
CREATE INDEX IF NOT EXISTS idx_growth_recommendations_org_priority
  ON public.growth_recommendations (organization_id, priority);
-- Back-link to the producing analysis.
CREATE INDEX IF NOT EXISTS idx_growth_recommendations_analysis
  ON public.growth_recommendations (source_analysis_id);

CREATE TRIGGER trg_growth_recommendations_updated_at
  BEFORE UPDATE ON public.growth_recommendations
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.growth_recommendations ENABLE ROW LEVEL SECURITY;

-- =====================================================================
-- ROLLBACK
-- =====================================================================
-- DROP INDEX IF EXISTS public.idx_growth_recommendations_analysis;
-- DROP INDEX IF EXISTS public.idx_growth_recommendations_org_priority;
-- DROP INDEX IF EXISTS public.idx_growth_recommendations_org_created;
-- DROP INDEX IF EXISTS public.idx_growth_recommendations_org_status;
-- DROP TABLE IF EXISTS public.growth_recommendations;
-- DROP TYPE IF EXISTS public.recommendation_status;
-- DROP TYPE IF EXISTS public.recommendation_priority;
-- =====================================================================
