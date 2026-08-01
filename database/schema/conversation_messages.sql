-- Append-only thread history.
CREATE TABLE IF NOT EXISTS public.conversation_messages (
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
