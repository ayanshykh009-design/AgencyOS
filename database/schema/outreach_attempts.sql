-- A single outreach send attempt with delivery tracking.
CREATE TABLE IF NOT EXISTS public.outreach_attempts (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id     uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  lead_id             uuid NOT NULL REFERENCES public.leads (id) ON DELETE CASCADE,
  outreach_message_id uuid REFERENCES public.outreach_messages (id) ON DELETE SET NULL,
  channel             public.outreach_channel NOT NULL,
  status              public.outreach_status NOT NULL DEFAULT 'queued',
  subject             text,
  body                text,
  scheduled_at        timestamptz,
  sent_at             timestamptz,
  delivered_at        timestamptz,
  external_id         text,
  error_code          text,
  error_message       text,
  metadata            jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT chk_outreach_attempts_timing
    CHECK (delivered_at IS NULL OR sent_at IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_outreach_attempts_org_lead
  ON public.outreach_attempts (organization_id, lead_id);
CREATE INDEX IF NOT EXISTS idx_outreach_attempts_org_status
  ON public.outreach_attempts (organization_id, status);
CREATE INDEX IF NOT EXISTS idx_outreach_attempts_org_scheduled
  ON public.outreach_attempts (organization_id, scheduled_at)
  WHERE status = 'queued';

DROP TRIGGER IF EXISTS trg_outreach_attempts_updated_at ON public.outreach_attempts;
CREATE TRIGGER trg_outreach_attempts_updated_at
  BEFORE UPDATE ON public.outreach_attempts
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
