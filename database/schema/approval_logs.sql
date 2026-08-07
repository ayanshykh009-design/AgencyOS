-- approval_logs: immutable approval audit trail (Phase 5D)
CREATE TABLE IF NOT EXISTS public.approval_logs (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id     uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  approval_request_id uuid NOT NULL REFERENCES public.approval_requests (id) ON DELETE CASCADE,
  actor_user_id       uuid REFERENCES public.users (id) ON DELETE SET NULL,
  action              public.approval_log_action NOT NULL,
  note                text,
  occurred_at         timestamptz NOT NULL DEFAULT now(),
  created_at          timestamptz NOT NULL DEFAULT now()
);

-- Per-request history (oldest first).
CREATE INDEX IF NOT EXISTS idx_approval_logs_request_occurred
  ON public.approval_logs (approval_request_id, occurred_at);
-- Tenant-scoped history listing.
CREATE INDEX IF NOT EXISTS idx_approval_logs_org_occurred
  ON public.approval_logs (organization_id, occurred_at DESC);

ALTER TABLE public.approval_logs ENABLE ROW LEVEL SECURITY;
