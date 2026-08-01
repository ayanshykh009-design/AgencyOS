-- =====================================================================
-- 0004_outreach_tables.sql
-- Message templates + delivery tracking: outreach_messages,
-- outreach_attempts, follow_ups, manual_outreach_queue.
-- =====================================================================

-- ---------------------------------------------------------------------
-- outreach_messages (reusable message templates per channel)
-- ---------------------------------------------------------------------
CREATE TABLE public.outreach_messages (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  name            text NOT NULL CHECK (length(btrim(name)) > 0),
  channel         public.outreach_channel NOT NULL,
  subject         text,
  body            text NOT NULL CHECK (length(btrim(body)) > 0),
  variables       jsonb NOT NULL DEFAULT '[]'::jsonb,
  version         integer NOT NULL DEFAULT 1 CHECK (version >= 1),
  is_active       boolean NOT NULL DEFAULT true,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_outreach_messages_org_name UNIQUE (organization_id, name)
);

CREATE INDEX idx_outreach_messages_org_channel
  ON public.outreach_messages (organization_id, channel);

CREATE TRIGGER trg_outreach_messages_updated_at
  BEFORE UPDATE ON public.outreach_messages
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------
-- outreach_attempts
-- ---------------------------------------------------------------------
CREATE TABLE public.outreach_attempts (
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
  external_id         text,   -- provider-side message id (never credentials)
  error_code          text,
  error_message       text,
  metadata            jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT chk_outreach_attempts_timing
    CHECK (delivered_at IS NULL OR sent_at IS NOT NULL)
);

CREATE INDEX idx_outreach_attempts_org_lead
  ON public.outreach_attempts (organization_id, lead_id);
CREATE INDEX idx_outreach_attempts_org_status
  ON public.outreach_attempts (organization_id, status);
CREATE INDEX idx_outreach_attempts_org_scheduled
  ON public.outreach_attempts (organization_id, scheduled_at)
  WHERE status = 'queued';

CREATE TRIGGER trg_outreach_attempts_updated_at
  BEFORE UPDATE ON public.outreach_attempts
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------
-- follow_ups
-- ---------------------------------------------------------------------
CREATE TABLE public.follow_ups (
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

CREATE INDEX idx_follow_ups_org_lead ON public.follow_ups (organization_id, lead_id);
CREATE INDEX idx_follow_ups_org_scheduled
  ON public.follow_ups (organization_id, scheduled_at)
  WHERE status = 'queued';

CREATE TRIGGER trg_follow_ups_updated_at
  BEFORE UPDATE ON public.follow_ups
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------
-- manual_outreach_queue (human-triggered outreach tasks)
-- ---------------------------------------------------------------------
CREATE TABLE public.manual_outreach_queue (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  lead_id         uuid NOT NULL REFERENCES public.leads (id) ON DELETE CASCADE,
  assigned_user_id uuid REFERENCES public.users (id) ON DELETE SET NULL,
  channel         public.outreach_channel NOT NULL,
  status          public.outreach_status NOT NULL DEFAULT 'queued',
  priority        smallint NOT NULL DEFAULT 0 CHECK (priority >= 0),
  due_at          timestamptz,
  subject         text,
  body            text,
  notes           text,
  completed_at    timestamptz,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_manual_outreach_org_lead
  ON public.manual_outreach_queue (organization_id, lead_id);
CREATE INDEX idx_manual_outreach_org_status_due
  ON public.manual_outreach_queue (organization_id, status, due_at);

CREATE TRIGGER trg_manual_outreach_queue_updated_at
  BEFORE UPDATE ON public.manual_outreach_queue
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------
ALTER TABLE public.outreach_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.outreach_attempts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.follow_ups ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.manual_outreach_queue ENABLE ROW LEVEL SECURITY;

-- =====================================================================
-- ROLLBACK
-- =====================================================================
-- DROP TABLE IF EXISTS public.manual_outreach_queue;
-- DROP TABLE IF EXISTS public.follow_ups;
-- DROP TABLE IF EXISTS public.outreach_attempts;
-- DROP TABLE IF EXISTS public.outreach_messages;
-- =====================================================================
