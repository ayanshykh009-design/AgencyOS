-- Append-only business audit trail (see activity_event_type).
CREATE TABLE IF NOT EXISTS public.activity_logs (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  user_id         uuid REFERENCES public.users (id) ON DELETE SET NULL,
  lead_id         uuid REFERENCES public.leads (id) ON DELETE SET NULL,
  event_type      public.activity_event_type NOT NULL,
  entity_type     text CHECK (entity_type IS NULL OR length(btrim(entity_type)) > 0),
  entity_id       uuid,
  description     text,
  metadata        jsonb NOT NULL DEFAULT '{}'::jsonb,
  occurred_at     timestamptz NOT NULL DEFAULT now(),
  created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_activity_logs_org_event
  ON public.activity_logs (organization_id, event_type, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_activity_logs_org_lead
  ON public.activity_logs (organization_id, lead_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_activity_logs_org_entity
  ON public.activity_logs (organization_id, entity_type, entity_id);
