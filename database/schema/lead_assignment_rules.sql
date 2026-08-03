-- Lead assignment rules: one per organization. Controls whether leads are
-- auto-assigned (round_robin/rules) and to whom (target_user_ids).
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
