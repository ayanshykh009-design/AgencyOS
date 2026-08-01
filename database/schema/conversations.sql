-- Reply threads; one open conversation per lead/channel at a time.
CREATE TABLE IF NOT EXISTS public.conversations (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id  uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  lead_id          uuid NOT NULL REFERENCES public.leads (id) ON DELETE CASCADE,
  channel          public.outreach_channel NOT NULL,
  external_thread_id text,
  subject          text,
  is_open          boolean NOT NULL DEFAULT true,
  last_message_at  timestamptz,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_conversations_external_thread
    UNIQUE (organization_id, channel, external_thread_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_conversations_open_per_channel
  ON public.conversations (lead_id, channel)
  WHERE is_open;

CREATE INDEX IF NOT EXISTS idx_conversations_org_lead ON public.conversations (organization_id, lead_id);
CREATE INDEX IF NOT EXISTS idx_conversations_org_updated ON public.conversations (organization_id, updated_at DESC);

DROP TRIGGER IF EXISTS trg_conversations_updated_at ON public.conversations;
CREATE TRIGGER trg_conversations_updated_at
  BEFORE UPDATE ON public.conversations
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
