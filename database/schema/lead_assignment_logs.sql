-- Lead assignment history: append-only ownership-change trail.
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
