-- notifications: in-app notification inbox (Phase 5D)
CREATE TABLE IF NOT EXISTS public.notifications (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  user_id         uuid REFERENCES public.users (id) ON DELETE SET NULL,
  type            public.notification_type NOT NULL,
  title           text NOT NULL,
  body            text NOT NULL,
  action_url      text,
  is_read         boolean NOT NULL DEFAULT false,
  read_at         timestamptz,
  metadata        jsonb NOT NULL DEFAULT '{}',
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT chk_notifications_title_not_blank CHECK (length(btrim(title)) > 0),
  CONSTRAINT chk_notifications_body_not_blank CHECK (length(btrim(body)) > 0)
);

-- Tenant inbox queries (incl. unread badge).
CREATE INDEX IF NOT EXISTS idx_notifications_org_user_read
  ON public.notifications (organization_id, user_id, is_read);
CREATE INDEX IF NOT EXISTS idx_notifications_user_unread
  ON public.notifications (user_id) WHERE is_read = false;
CREATE INDEX IF NOT EXISTS idx_notifications_org_created
  ON public.notifications (organization_id, created_at DESC);
-- Retention sweep.
CREATE INDEX IF NOT EXISTS idx_notifications_created_retention
  ON public.notifications (created_at);

DROP TRIGGER IF EXISTS trg_notifications_updated_at ON public.notifications;
CREATE TRIGGER trg_notifications_updated_at
  BEFORE UPDATE ON public.notifications
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;
