-- Human-triggered (manual) outreach tasks queued for a user.
CREATE TABLE IF NOT EXISTS public.manual_outreach_queue (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id  uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  lead_id          uuid NOT NULL REFERENCES public.leads (id) ON DELETE CASCADE,
  assigned_user_id uuid REFERENCES public.users (id) ON DELETE SET NULL,
  channel          public.outreach_channel NOT NULL,
  status           public.outreach_status NOT NULL DEFAULT 'queued',
  priority         smallint NOT NULL DEFAULT 0 CHECK (priority >= 0),
  due_at           timestamptz,
  subject          text,
  body             text,
  notes            text,
  completed_at     timestamptz,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_manual_outreach_org_lead
  ON public.manual_outreach_queue (organization_id, lead_id);
CREATE INDEX IF NOT EXISTS idx_manual_outreach_org_status_due
  ON public.manual_outreach_queue (organization_id, status, due_at);

DROP TRIGGER IF EXISTS trg_manual_outreach_queue_updated_at ON public.manual_outreach_queue;
CREATE TRIGGER trg_manual_outreach_queue_updated_at
  BEFORE UPDATE ON public.manual_outreach_queue
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
