-- Reusable outreach message templates per channel.
CREATE TABLE IF NOT EXISTS public.outreach_messages (
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

CREATE INDEX IF NOT EXISTS idx_outreach_messages_org_channel
  ON public.outreach_messages (organization_id, channel);

DROP TRIGGER IF EXISTS trg_outreach_messages_updated_at ON public.outreach_messages;
CREATE TRIGGER trg_outreach_messages_updated_at
  BEFORE UPDATE ON public.outreach_messages
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
