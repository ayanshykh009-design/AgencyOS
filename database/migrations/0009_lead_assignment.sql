-- =====================================================================
-- 0009_lead_assignment.sql
-- Lead assignment engine: per-org rules + append-only assignment history.
--
--   * assignment_strategy: manual | round_robin | rules
--   * assignment_method:   manual | round_robin | rules | bulk | unassigned
--   * lead_assignment_rules: one rule per org (targets + optional source
--     conditions for the RULES strategy, plus the round-robin cursor).
--   * lead_assignment_logs: immutable ownership-change trail.
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

SELECT public.agencyos_create_enum(
  'assignment_strategy', ARRAY['manual', 'round_robin', 'rules']
);
SELECT public.agencyos_create_enum(
  'assignment_method', ARRAY['manual', 'round_robin', 'rules', 'bulk', 'unassigned']
);

DROP FUNCTION public.agencyos_create_enum(text, text[]);

-- ---------------------------------------------------------------------
-- lead_assignment_rules
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.lead_assignment_rules (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id      uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  name                 text NOT NULL CHECK (length(btrim(name)) > 0),
  strategy             public.assignment_strategy NOT NULL DEFAULT 'manual',
  enabled              boolean NOT NULL DEFAULT false,
  target_user_ids      jsonb NOT NULL DEFAULT '[]'::jsonb,
  conditions           jsonb NOT NULL DEFAULT '{}'::jsonb,
  last_assigned_index  integer NOT NULL DEFAULT -1 CHECK (last_assigned_index >= -1),
  created_at           timestamptz NOT NULL DEFAULT now(),
  updated_at           timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_lead_assignment_rules_org UNIQUE (organization_id)
);

CREATE INDEX IF NOT EXISTS idx_lead_assignment_rules_org ON public.lead_assignment_rules (organization_id);

DROP TRIGGER IF EXISTS trg_lead_assignment_rules_updated_at ON public.lead_assignment_rules;

CREATE TRIGGER trg_lead_assignment_rules_updated_at
  BEFORE UPDATE ON public.lead_assignment_rules
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------
-- lead_assignment_logs
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.lead_assignment_logs (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id      uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  lead_id              uuid NOT NULL REFERENCES public.leads (id) ON DELETE CASCADE,
  from_user_id         uuid REFERENCES public.users (id) ON DELETE SET NULL,
  to_user_id           uuid REFERENCES public.users (id) ON DELETE SET NULL,
  method               public.assignment_method NOT NULL,
  assigned_by_user_id  uuid REFERENCES public.users (id) ON DELETE SET NULL,
  reason               text,
  created_at           timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_lead_assignment_logs_org ON public.lead_assignment_logs (organization_id);
CREATE INDEX IF NOT EXISTS idx_lead_assignment_logs_lead ON public.lead_assignment_logs (lead_id);
CREATE INDEX IF NOT EXISTS idx_lead_assignment_logs_created ON public.lead_assignment_logs (created_at DESC);

ALTER TABLE public.lead_assignment_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.lead_assignment_logs ENABLE ROW LEVEL SECURITY;

-- =====================================================================
-- ROLLBACK
-- =====================================================================
-- DROP TABLE IF EXISTS public.lead_assignment_logs;
-- DROP TABLE IF EXISTS public.lead_assignment_rules;
-- DROP TYPE IF EXISTS public.assignment_method;
-- DROP TYPE IF EXISTS public.assignment_strategy;
-- =====================================================================
