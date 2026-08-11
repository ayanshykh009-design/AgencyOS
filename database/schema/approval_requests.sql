-- approval_requests: workflow-gated approval requests (Phase 5D)
CREATE TABLE IF NOT EXISTS public.approval_requests (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id       uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  workflow_id           uuid REFERENCES public.workflows (id) ON DELETE SET NULL,
  workflow_execution_id uuid REFERENCES public.workflow_executions (id) ON DELETE SET NULL,
  requested_by_user_id  uuid REFERENCES public.users (id) ON DELETE SET NULL,
  approver_user_id      uuid REFERENCES public.users (id) ON DELETE SET NULL,
  title                 text NOT NULL,
  details               text,
  status                public.approval_request_status NOT NULL DEFAULT 'pending',
  expires_at            timestamptz NOT NULL DEFAULT (now() + interval '24 hours'),
  decided_by_user_id    uuid REFERENCES public.users (id) ON DELETE SET NULL,
  decided_at            timestamptz,
  decision_note         text,
  gate_handled_at       timestamptz,
  created_at            timestamptz NOT NULL DEFAULT now(),
  updated_at            timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT chk_approval_requests_title_not_blank CHECK (length(btrim(title)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_approval_requests_org_status
  ON public.approval_requests (organization_id, status);
CREATE INDEX IF NOT EXISTS idx_approval_requests_org_approver_status
  ON public.approval_requests (organization_id, approver_user_id, status);
CREATE INDEX IF NOT EXISTS idx_approval_requests_org_created
  ON public.approval_requests (organization_id, created_at DESC);
-- Pending-expiry sweep.
CREATE INDEX IF NOT EXISTS idx_approval_requests_pending_expiry
  ON public.approval_requests (expires_at) WHERE status = 'pending';
-- FK support (execution-gated approvals).
CREATE INDEX IF NOT EXISTS idx_approval_requests_execution
  ON public.approval_requests (workflow_execution_id);
-- Gate-worker sweep: terminal requests whose gate has not been handled yet.
CREATE INDEX IF NOT EXISTS idx_approval_requests_gate_handled
  ON public.approval_requests (status)
  WHERE gate_handled_at IS NULL AND workflow_execution_id IS NOT NULL;

DROP TRIGGER IF EXISTS trg_approval_requests_updated_at ON public.approval_requests;
CREATE TRIGGER trg_approval_requests_updated_at
  BEFORE UPDATE ON public.approval_requests
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.approval_requests ENABLE ROW LEVEL SECURITY;
