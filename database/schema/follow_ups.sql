-- Scheduled follow-up messages in an outreach sequence.
CREATE TABLE IF NOT EXISTS public.follow_ups (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id     uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  lead_id             uuid NOT NULL REFERENCES public.leads (id) ON DELETE CASCADE,
  outreach_attempt_id uuid REFERENCES public.outreach_attempts (id) ON DELETE CASCADE,
  channel             public.outreach_channel NOT NULL,
  sequence_position   integer NOT NULL CHECK (sequence_position >= 1),
  subject             text,
  body                text NOT NULL CHECK (length(btrim(body)) > 0),
  delay_days          integer NOT NULL DEFAULT 0 CHECK (delay_days >= 0),
  scheduled_at        timestamptz,
  status              public.outreach_status NOT NULL DEFAULT 'queued',
  sent_at             timestamptz,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_follow_ups_position
    UNIQUE (lead_id, outreach_attempt_id, sequence_position)
);

CREATE INDEX IF NOT EXISTS idx_follow_ups_org_lead ON public.follow_ups (organization_id, lead_id);
CREATE INDEX IF NOT EXISTS idx_follow_ups_org_scheduled
  ON public.follow_ups (organization_id, scheduled_at)
  WHERE status = 'queued';

DROP TRIGGER IF EXISTS trg_follow_ups_updated_at ON public.follow_ups;
CREATE TRIGGER trg_follow_ups_updated_at
  BEFORE UPDATE ON public.follow_ups
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
