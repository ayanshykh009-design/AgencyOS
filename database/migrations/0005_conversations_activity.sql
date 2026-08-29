-- =====================================================================
-- 0005_conversations_activity.sql
-- Reply threads + business audit trail: conversations,
-- conversation_messages, activity_logs.
-- =====================================================================

-- ---------------------------------------------------------------------
-- conversations
-- ---------------------------------------------------------------------
CREATE TABLE public.conversations (
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

-- A lead has at most one OPEN conversation per channel.
CREATE UNIQUE INDEX IF NOT EXISTS uq_conversations_open_per_channel
  ON public.conversations (lead_id, channel)
  WHERE is_open;

CREATE INDEX IF NOT EXISTS idx_conversations_org_lead ON public.conversations (organization_id, lead_id);
CREATE INDEX IF NOT EXISTS idx_conversations_org_updated ON public.conversations (organization_id, updated_at DESC);

DROP TRIGGER IF EXISTS trg_conversations_updated_at ON public.conversations;

CREATE TRIGGER trg_conversations_updated_at
  BEFORE UPDATE ON public.conversations
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------
-- conversation_messages (append-only thread history)
-- ---------------------------------------------------------------------
CREATE TABLE public.conversation_messages (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id  uuid NOT NULL REFERENCES public.conversations (id) ON DELETE CASCADE,
  organization_id  uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  sender_type      public.conversation_sender NOT NULL,
  sender_user_id   uuid REFERENCES public.users (id) ON DELETE SET NULL,
  body             text NOT NULL CHECK (length(btrim(body)) > 0),
  external_id      text,
  metadata         jsonb NOT NULL DEFAULT '{}'::jsonb,
  sent_at          timestamptz NOT NULL DEFAULT now(),
  created_at       timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_conversation_messages_thread
  ON public.conversation_messages (conversation_id, sent_at);
CREATE INDEX IF NOT EXISTS idx_conversation_messages_org
  ON public.conversation_messages (organization_id, sent_at DESC);

-- ---------------------------------------------------------------------
-- activity_logs (append-only business audit trail)
-- ---------------------------------------------------------------------
CREATE TABLE public.activity_logs (
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

-- ---------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------
ALTER TABLE public.conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.conversation_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.activity_logs ENABLE ROW LEVEL SECURITY;

-- =====================================================================
-- ROLLBACK
-- =====================================================================
-- DROP TABLE IF EXISTS public.activity_logs;
-- DROP TABLE IF EXISTS public.conversation_messages;
-- DROP TABLE IF EXISTS public.conversations;
-- =====================================================================
