-- deliveries: the delivery outbox (Phase M6)
-- Every outbound founder communication is recorded here first; the delivery
-- worker moves rows through the state machine
-- (queued -> processing -> delivered | failed | cancelled; processing -> retrying -> queued | cancelled).
-- Cooperative cancellation: a PROCESSING delivery keeps its row and is flagged
-- via cancel_requested_at/cancelled_by_user_id; the worker honours the flag
-- when the provider returns (delivered always wins over a cancel request).
-- attempt_started_at backs the stale-processing recovery sweep.
CREATE TABLE IF NOT EXISTS public.deliveries (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id     uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  channel             public.delivery_channel NOT NULL,
  recipient_user_id   uuid REFERENCES public.users (id) ON DELETE SET NULL,
  notification_id     uuid REFERENCES public.notifications (id) ON DELETE SET NULL,
  approval_request_id uuid REFERENCES public.approval_requests (id) ON DELETE SET NULL,
  subject             text NOT NULL,
  body                text NOT NULL,
  action_url          text,
  status              public.delivery_status NOT NULL DEFAULT 'queued',
  attempts            integer NOT NULL DEFAULT 0,
  max_attempts        integer NOT NULL DEFAULT 4,
  next_attempt_at     timestamptz,
  attempt_started_at  timestamptz,
  cancel_requested_at timestamptz,
  cancelled_by_user_id uuid REFERENCES public.users (id) ON DELETE SET NULL,
  last_error          text,
  provider_metadata   jsonb NOT NULL DEFAULT '{}',
  payload             jsonb NOT NULL DEFAULT '{}',
  idempotency_key     text,
  scheduled_for       timestamptz NOT NULL DEFAULT now(),
  delivered_at        timestamptz,
  failed_at           timestamptz,
  cancelled_at        timestamptz,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT chk_deliveries_subject_not_blank CHECK (length(btrim(subject)) > 0),
  CONSTRAINT chk_deliveries_body_not_blank CHECK (length(btrim(body)) > 0),
  CONSTRAINT chk_deliveries_attempts_nonneg CHECK (attempts >= 0),
  CONSTRAINT chk_deliveries_max_attempts_positive CHECK (max_attempts > 0),
  CONSTRAINT chk_deliveries_cancel_request_has_actor
    CHECK (cancel_requested_at IS NULL OR cancelled_by_user_id IS NOT NULL)
);

-- Tenant-scoped lookups (org inbox, status filters, badge queries).
CREATE INDEX IF NOT EXISTS idx_deliveries_org_status
  ON public.deliveries (organization_id, status);
CREATE INDEX IF NOT EXISTS idx_deliveries_org_created
  ON public.deliveries (organization_id, created_at DESC);
-- Per-recipient history.
CREATE INDEX IF NOT EXISTS idx_deliveries_org_recipient_status
  ON public.deliveries (organization_id, recipient_user_id, status);
-- Worker sweep: due outbox rows (fair-drain + retry backoff).
CREATE INDEX IF NOT EXISTS idx_deliveries_queued_next_attempt
  ON public.deliveries (next_attempt_at)
  WHERE status IN ('queued', 'processing');
-- Retry promotion: due RETRYING rows are moved back to QUEUED by the worker.
CREATE INDEX IF NOT EXISTS idx_deliveries_retrying_next_attempt
  ON public.deliveries (next_attempt_at)
  WHERE status = 'retrying';
-- Stale-processing recovery sweep (recover rows stuck past the window).
CREATE INDEX IF NOT EXISTS idx_deliveries_processing_attempt_started
  ON public.deliveries (attempt_started_at)
  WHERE status = 'processing';
-- Retry-safe enqueue.
CREATE UNIQUE INDEX IF NOT EXISTS uq_deliveries_org_idempotency
  ON public.deliveries (organization_id, idempotency_key)
  WHERE idempotency_key IS NOT NULL;
-- FK support (approval-gate announcements + inbox links).
CREATE INDEX IF NOT EXISTS idx_deliveries_approval_request
  ON public.deliveries (approval_request_id);
CREATE INDEX IF NOT EXISTS idx_deliveries_notification
  ON public.deliveries (notification_id);

DROP TRIGGER IF EXISTS trg_deliveries_updated_at ON public.deliveries;
CREATE TRIGGER trg_deliveries_updated_at
  BEFORE UPDATE ON public.deliveries
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.deliveries ENABLE ROW LEVEL SECURITY;
