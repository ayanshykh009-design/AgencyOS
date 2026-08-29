-- =====================================================================
-- 0010_pipeline_management.sql
-- Pipeline (Kanban) overlay: org-scoped stages + close reasons.
--
-- The pipeline is an overlay on the fixed lead_status lifecycle:
--   * stage_lifecycle: open | won | lost (coarse bucket).
--   * pipeline_stages: one column per org; seeded defaults mirror the
--     open statuses plus won/lost. Each lifecycle has a marked default.
--   * close_reasons: labelled won/lost closure reasons per org.
--   * leads gains stage_id / close_reason_id / won_at / lost_at /
--     deal_value (revenue for analytics).
--
-- Existing leads are backfilled: stage matched by name==status, and won/lost
-- timestamps approximated with updated_at. All statements are idempotent so
-- CI can re-apply them against a live database.
-- =====================================================================

-- ---------------------------------------------------------------------
-- enums
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.agencyos_create_enum(p_name text, p_values text[])
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
  v_expr text;
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'public' AND t.typname = p_name
  ) THEN
    SELECT string_agg(quote_literal(v), ', ' ORDER BY ord)
      INTO v_expr
      FROM unnest(p_values) WITH ORDINALITY AS x(v, ord);
    EXECUTE format('CREATE TYPE public.%I AS ENUM (%s)', p_name, v_expr);
  END IF;
END;
$$;

SELECT public.agencyos_create_enum('stage_lifecycle', ARRAY['open', 'won', 'lost']);

DROP FUNCTION public.agencyos_create_enum(text, text[]);

-- ---------------------------------------------------------------------
-- pipeline_stages
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.pipeline_stages (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id      uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  name                 text NOT NULL CHECK (length(btrim(name)) > 0),
  lifecycle            public.stage_lifecycle NOT NULL DEFAULT 'open',
  position             integer NOT NULL DEFAULT 0,
  is_default           boolean NOT NULL DEFAULT false,
  created_at           timestamptz NOT NULL DEFAULT now(),
  updated_at           timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_pipeline_stages_org_lifecycle_name
    UNIQUE (organization_id, lifecycle, name)
);

CREATE INDEX IF NOT EXISTS idx_pipeline_stages_org_position
  ON public.pipeline_stages (organization_id, position);

DROP TRIGGER IF EXISTS trg_pipeline_stages_updated_at ON public.pipeline_stages;

CREATE TRIGGER trg_pipeline_stages_updated_at
  BEFORE UPDATE ON public.pipeline_stages
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------
-- close_reasons
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.close_reasons (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id      uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  lifecycle            public.stage_lifecycle NOT NULL,
  name                 text NOT NULL CHECK (length(btrim(name)) > 0),
  is_default           boolean NOT NULL DEFAULT false,
  created_at           timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_close_reasons_org_lifecycle_name
    UNIQUE (organization_id, lifecycle, name),
  CONSTRAINT chk_close_reasons_lifecycle CHECK (lifecycle IN ('won', 'lost'))
);

CREATE INDEX IF NOT EXISTS idx_close_reasons_org ON public.close_reasons (organization_id);

-- ---------------------------------------------------------------------
-- leads: pipeline placement + win/loss bookkeeping
-- ---------------------------------------------------------------------
ALTER TABLE public.leads
  ADD COLUMN IF NOT EXISTS stage_id uuid REFERENCES public.pipeline_stages (id) ON DELETE SET NULL;
ALTER TABLE public.leads
  ADD COLUMN IF NOT EXISTS close_reason_id uuid REFERENCES public.close_reasons (id) ON DELETE SET NULL;
ALTER TABLE public.leads
  ADD COLUMN IF NOT EXISTS won_at timestamptz;
ALTER TABLE public.leads
  ADD COLUMN IF NOT EXISTS lost_at timestamptz;
ALTER TABLE public.leads
  ADD COLUMN IF NOT EXISTS deal_value numeric(14, 2) CHECK (deal_value IS NULL OR deal_value >= 0);

CREATE INDEX IF NOT EXISTS idx_leads_org_stage ON public.leads (organization_id, stage_id);
CREATE INDEX IF NOT EXISTS idx_leads_org_close_reason
  ON public.leads (organization_id, close_reason_id);

-- ---------------------------------------------------------------------
-- backfill: seed default stages for orgs without any, then map leads
-- ---------------------------------------------------------------------
INSERT INTO public.pipeline_stages (organization_id, name, lifecycle, position, is_default)
SELECT o.id, s.name, s.lifecycle::public.stage_lifecycle, s.position, s.is_default
FROM public.organizations o
CROSS JOIN (
  VALUES
    ('new', 'open', 0, TRUE),
    ('researching', 'open', 1, FALSE),
    ('contacted', 'open', 2, FALSE),
    ('meeting_booked', 'open', 3, FALSE),
    ('proposal_sent', 'open', 4, FALSE),
    ('won', 'won', 5, TRUE),
    ('lost', 'lost', 6, TRUE)
) AS s(name, lifecycle, position, is_default)
WHERE NOT EXISTS (
  SELECT 1 FROM public.pipeline_stages ps WHERE ps.organization_id = o.id
);

-- Map every existing lead to its status-matching stage (name == status).
UPDATE public.leads l
SET stage_id = ps.id
FROM public.pipeline_stages ps
WHERE ps.organization_id = l.organization_id
  AND ps.name = l.status::text
  AND l.stage_id IS NULL;

-- Approximate closure timestamps for historical won/lost leads.
UPDATE public.leads SET won_at = updated_at WHERE status = 'won' AND won_at IS NULL;
UPDATE public.leads SET lost_at = updated_at WHERE status = 'lost' AND lost_at IS NULL;

-- ---------------------------------------------------------------------
-- row level security
-- ---------------------------------------------------------------------
ALTER TABLE public.pipeline_stages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.close_reasons ENABLE ROW LEVEL SECURITY;

-- =====================================================================
-- ROLLBACK
-- =====================================================================
-- ALTER TABLE public.leads DROP COLUMN IF EXISTS deal_value;
-- ALTER TABLE public.leads DROP COLUMN IF EXISTS lost_at;
-- ALTER TABLE public.leads DROP COLUMN IF EXISTS won_at;
-- ALTER TABLE public.leads DROP COLUMN IF EXISTS close_reason_id;
-- ALTER TABLE public.leads DROP COLUMN IF EXISTS stage_id;
-- DROP TABLE IF EXISTS public.close_reasons;
-- DROP TABLE IF EXISTS public.pipeline_stages;
-- DROP TYPE IF EXISTS public.stage_lifecycle;
-- =====================================================================
