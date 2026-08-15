-- Mirror of the three new M8 tables (enums live in migrations/enums/14_founder.sql).

CREATE TABLE IF NOT EXISTS public.founder_conversations (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id     uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  title               text,
  is_archived         bool NOT NULL DEFAULT false,
  last_message_at     timestamptz,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT chk_founder_conversations_title_not_blank CHECK (
    title IS NULL OR length(btrim(title)) > 0
  )
);

CREATE TABLE IF NOT EXISTS public.founder_messages (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id     uuid NOT NULL REFERENCES public.founder_conversations (id) ON DELETE CASCADE,
  organization_id     uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  sender_type         public.founder_message_sender NOT NULL,
  sender_user_id      uuid,
  body                text NOT NULL,
  metadata_           jsonb NOT NULL DEFAULT '{}',
  sent_at             timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT chk_founder_messages_body_not_blank CHECK (length(btrim(body)) > 0),
  CONSTRAINT fk_founder_messages_sender FOREIGN KEY (sender_user_id) REFERENCES public.users (id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS public.founder_action_proposals (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id     uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  conversation_id     uuid REFERENCES public.founder_conversations (id) ON DELETE SET NULL,
  agent_run_id        uuid REFERENCES public.agent_runs (id) ON DELETE SET NULL,
  approval_request_id uuid REFERENCES public.approval_requests (id) ON DELETE SET NULL,
  proposal_status     public.founder_proposal_status NOT NULL DEFAULT 'proposed',
  action_type         public.founder_action_type NOT NULL,
  title               text NOT NULL,
  payload             jsonb NOT NULL DEFAULT '{}',
  justification        text,
  expires_at          timestamptz,
  decided_at          timestamptz,
  decided_by_user_id  uuid REFERENCES public.users (id) ON DELETE SET NULL,
  actor_user_id       uuid NOT NULL REFERENCES public.users (id) ON DELETE CASCADE,
  execution_reference jsonb,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT chk_founder_action_proposals_title_not_blank CHECK (length(btrim(title)) > 0),
  CONSTRAINT chk_founder_action_proposals_payload_size CHECK (octet_length(payload::text) <= 16384)
);

CREATE INDEX IF NOT EXISTS idx_founder_conversations_org_created
  ON public.founder_conversations (organization_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_founder_conversations_org_archive
  ON public.founder_conversations (organization_id, is_archived, last_message_at);

CREATE INDEX IF NOT EXISTS idx_founder_messages_conversation_sent
  ON public.founder_messages (conversation_id, sent_at);
CREATE INDEX IF NOT EXISTS idx_founder_messages_org_sent
  ON public.founder_messages (organization_id, sent_at DESC);

CREATE INDEX IF NOT EXISTS idx_founder_action_proposals_org_status
  ON public.founder_action_proposals (organization_id, proposal_status);
CREATE INDEX IF NOT EXISTS idx_founder_action_proposals_org_created
  ON public.founder_action_proposals (organization_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_founder_action_proposals_approval_request
  ON public.founder_action_proposals (approval_request_id) WHERE approval_request_id IS NOT NULL;

CREATE TRIGGER trg_founder_conversations_updated_at
  BEFORE UPDATE ON public.founder_conversations
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER trg_founder_action_proposals_updated_at
  BEFORE UPDATE ON public.founder_action_proposals
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.founder_conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.founder_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.founder_action_proposals ENABLE ROW LEVEL SECURITY;
