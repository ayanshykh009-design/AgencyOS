-- =====================================================================
-- 0027_m9_intelligence_signals.sql
-- Phase M9: Founder Intelligence & Growth Triage — triage/orchestration.
--
--   * signal_category / signal_source_type / intelligence_signal_status
--     / intelligence_signal_severity / intelligence_confidence — labels
--   * intelligence_signals — a single, deduplicated, scored signal feed
--     that surfaces M7/M8 output (growth_recommendations, business_insights,
--     growth_analyses findings, bounded pipeline condition detectors) to the
--     founder.
--
-- M9 never writes source tables. It reads M7/M8 results and materializes a
-- deterministic triage view: every row carries a versioned ``priority_score``
-- (sum of weighted components in ``priority_components``) plus optional
-- handoff fields (``last_notified_at``, ``acknowledged_*``) so the worker can
-- notify exactly once and the UI can reason about the full lifecycle.
--
-- Deduplication: ``content_hash`` is deterministic per source row, and the
-- partial unique index ``(organization_id, content_hash) WHERE status <>
-- 'superseded'`` makes a single live signal per source the invariant (the
-- triage worker upserts on this key).
--
-- Backward compatibility: additive only (new enum types + new table).
-- =====================================================================

-- ---------------------------------------------------------------------
-- signal_category: what kind of business signal this is.
-- ---------------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'public' AND t.typname = 'signal_category'
  ) THEN
    CREATE TYPE public.signal_category AS ENUM (
      'growth_recommendation', 'business_insight', 'pipeline_risk',
      'pipeline_opportunity', 'growth_anomaly', 'founder_briefing'
    );
  END IF;
END;
$$;

-- ---------------------------------------------------------------------
-- signal_source_type: which M7/M8/pipeline table produced the signal.
-- ---------------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'public' AND t.typname = 'signal_source_type'
  ) THEN
    CREATE TYPE public.signal_source_type AS ENUM (
      'growth_recommendation', 'business_insight', 'growth_analysis',
      'pipeline_fact', 'briefing'
    );
  END IF;
END;
$$;

-- ---------------------------------------------------------------------
-- intelligence_signal_status: triage lifecycle of a signal.
--   active -> acknowledged | dismissed
--   active -> superseded (source no longer warrants attention)
-- ---------------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'public' AND t.typname = 'intelligence_signal_status'
  ) THEN
    CREATE TYPE public.intelligence_signal_status AS ENUM (
      'active', 'acknowledged', 'dismissed', 'superseded'
    );
  END IF;
END;
$$;

-- ---------------------------------------------------------------------
-- intelligence_signal_severity: urgency of the underlying finding.
-- ---------------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'public' AND t.typname = 'intelligence_signal_severity'
  ) THEN
    CREATE TYPE public.intelligence_signal_severity AS ENUM (
      'info', 'low', 'medium', 'high', 'critical'
    );
  END IF;
END;
$$;

-- ---------------------------------------------------------------------
-- intelligence_confidence: qualitative confidence in the signal itself.
-- ---------------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'public' AND t.typname = 'intelligence_confidence'
  ) THEN
    CREATE TYPE public.intelligence_confidence AS ENUM (
      'low', 'medium', 'high'
    );
  END IF;
END;
$$;

CREATE TABLE IF NOT EXISTS public.intelligence_signals (
  id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id         uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  signal_category         public.signal_category NOT NULL,
  source_type             public.signal_source_type NOT NULL,
  source_row_id           uuid,
  title                   text NOT NULL,
  summary                 text NOT NULL,
  severity                public.intelligence_signal_severity NOT NULL DEFAULT 'info',
  business_impact         jsonb NOT NULL DEFAULT '{}',
  priority_score          numeric(5,4) NOT NULL DEFAULT 0,
  priority_components     jsonb NOT NULL DEFAULT '{}',
  evidence                jsonb NOT NULL DEFAULT '[]',
  recommended_next_step   text,
  confidence              public.intelligence_confidence NOT NULL DEFAULT 'low',
  status                  public.intelligence_signal_status NOT NULL DEFAULT 'active',
  content_hash            text NOT NULL,
  first_seen_at           timestamptz NOT NULL DEFAULT now(),
  last_triaged_at         timestamptz,
  acknowledged_by_user_id uuid REFERENCES public.users (id) ON DELETE SET NULL,
  acknowledged_at         timestamptz,
  last_notified_at        timestamptz,
  created_at              timestamptz NOT NULL DEFAULT now(),
  updated_at              timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT chk_intelligence_signals_title_not_blank CHECK (length(btrim(title)) > 0),
  CONSTRAINT chk_intelligence_signals_summary_not_blank CHECK (length(btrim(summary)) > 0),
  CONSTRAINT chk_intelligence_signals_hash_not_blank CHECK (length(btrim(content_hash)) > 0),
  CONSTRAINT chk_intelligence_signals_priority_range CHECK (
    priority_score >= 0 AND priority_score <= 1
  )
);

-- Indexes
-- At most one live (non-superseded) signal per deterministic content hash:
-- the triage worker upserts on this key, so concurrent sweeps can never
-- create duplicate signals for the same source row.
CREATE UNIQUE INDEX IF NOT EXISTS uq_intelligence_signals_org_hash_active
  ON public.intelligence_signals (organization_id, content_hash)
  WHERE status <> 'superseded';

-- Triage surface: founder feed ordered by priority.
CREATE INDEX IF NOT EXISTS idx_intelligence_signals_org_status_priority
  ON public.intelligence_signals (organization_id, status, priority_score DESC);

-- Source lineage lookups (re-triage superseding, dedup scans).
CREATE INDEX IF NOT EXISTS idx_intelligence_signals_org_source
  ON public.intelligence_signals (organization_id, source_type, source_row_id)
  WHERE source_row_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_intelligence_signals_org_created
  ON public.intelligence_signals (organization_id, created_at DESC);

-- Triggers
CREATE TRIGGER trg_intelligence_signals_updated_at
  BEFORE UPDATE ON public.intelligence_signals
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- RLS enabled on the table; org-scoped policies ship with the policy set.
ALTER TABLE public.intelligence_signals ENABLE ROW LEVEL SECURITY;
