-- =====================================================================
-- 0020_m6_delivery.sql
-- Phase M6: Founder Communication & Delivery Layer — delivery outbox.
--
--   * delivery_channel / delivery_status / delivery_event_type — labels
--   * deliveries                             — the delivery outbox (org-scoped)
--   * delivery_events                        — append-only delivery timeline
--
-- Backward compatibility:
--   * additive only (new enum types + new tables; nothing existing is touched)
--   * CREATE TABLE / INDEX / TRIGGER IF NOT EXISTS are idempotent
--   * enum creation guarded by pg_type existence checks
--   * safe to run multiple times; zero data loss
-- =====================================================================

-- ---------------------------------------------------------------------
-- delivery_channel: the transport a delivery is sent over.
-- M6 ships the dashboard provider only; email/whatsapp/push are declared
-- for the frozen M1 surface and fail closed until their providers land in
-- later milestones.
-- ---------------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'public' AND t.typname = 'delivery_channel'
  ) THEN
    CREATE TYPE public.delivery_channel AS ENUM (
      'dashboard', 'email', 'whatsapp', 'push'
    );
  END IF;
END;
$$;

-- ---------------------------------------------------------------------
-- delivery_status: lifecycle of a single delivery (outbox state machine).
--
--   queued -> processing -> delivered | failed | cancelled
--              \--> retrying -> queued | cancelled
--   failed/cancelled -> queued only via an explicit manual retry
-- ---------------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'public' AND t.typname = 'delivery_status'
  ) THEN
    CREATE TYPE public.delivery_status AS ENUM (
      'queued', 'processing', 'delivered', 'retrying', 'failed', 'cancelled'
    );
  END IF;
END;
$$;

-- ---------------------------------------------------------------------
-- delivery_event_type: append-only timeline labels for a delivery.
--
--   queued               enqueued into the outbox
--   claimed              a worker took ownership (queued -> processing)
--   provider_dispatched  provider called with the message
--   provider_returned    provider returned a result for the attempt
--   delivered            terminal success
--   retrying             a retry was scheduled (processing -> retrying)
--   failed               terminal failure
--   cancelled            terminal cancellation
--   timed_out            the attempt exceeded the active provider timeout
--   recovery_guard       guard event stamped before a stale row is recovered
--   superseded           reserved: a newer delivery replaced this one
-- ---------------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'public' AND t.typname = 'delivery_event_type'
  ) THEN
    CREATE TYPE public.delivery_event_type AS ENUM (
      'queued', 'claimed', 'provider_dispatched', 'provider_returned',
      'delivered', 'retrying', 'failed', 'cancelled', 'timed_out',
      'recovery_guard', 'superseded'
    );
  END IF;
END;
$$;

-- ---------------------------------------------------------------------
-- deliveries: the delivery outbox (org-scoped).
--
-- Every outbound founder communication is recorded here first; the delivery
-- worker moves rows through the state machine (see ``delivery_status``).
-- ``scheduled_for``/``next_attempt_at`` back the fair-drain sweep and the
-- per-org pending cap; ``idempotency_key`` makes enqueue retry-safe;
-- ``notification_id``/``approval_request_id`` link a delivery to the inbox
-- row it created or the approval gate it announces.
--
-- Cooperative cancellation: a PROCESSING delivery keeps its row and is flagged
-- via ``cancel_requested_at``/``cancelled_by_user_id``; the worker honours the
-- flag when the provider returns (delivered always wins over a cancel request).
-- ``attempt_started_at`` backs the stale-processing recovery sweep
-- (recover rows stuck longer than DELIVERY_RECOVERY_SECONDS).
-- ---------------------------------------------------------------------
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

CREATE TRIGGER trg_deliveries_updated_at
  BEFORE UPDATE ON public.deliveries
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.deliveries ENABLE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------
-- delivery_events: immutable per-delivery timeline (append-only).
-- Rows are never updated or deleted; no updated_at, no write policies.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.delivery_events (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  delivery_id     uuid NOT NULL REFERENCES public.deliveries (id) ON DELETE CASCADE,
  event_type      public.delivery_event_type NOT NULL,
  attempt         integer NOT NULL DEFAULT 0,
  metadata        jsonb NOT NULL DEFAULT '{}',
  occurred_at     timestamptz NOT NULL DEFAULT now(),
  created_at      timestamptz NOT NULL DEFAULT now()
);

-- Per-delivery history (oldest first).
CREATE INDEX IF NOT EXISTS idx_delivery_events_delivery_occurred
  ON public.delivery_events (delivery_id, occurred_at);
-- Tenant-scoped timeline listing.
CREATE INDEX IF NOT EXISTS idx_delivery_events_org_occurred
  ON public.delivery_events (organization_id, occurred_at DESC);
-- Retention sweep (prune events older than DELIVERY_EVENT_RETENTION_DAYS).
CREATE INDEX IF NOT EXISTS idx_delivery_events_occurred
  ON public.delivery_events (occurred_at);

ALTER TABLE public.delivery_events ENABLE ROW LEVEL SECURITY;

-- =====================================================================
-- ROLLBACK
-- =====================================================================
-- DROP INDEX IF EXISTS public.idx_delivery_events_occurred;
-- DROP INDEX IF EXISTS public.idx_delivery_events_org_occurred;
-- DROP INDEX IF EXISTS public.idx_delivery_events_delivery_occurred;
-- DROP INDEX IF EXISTS public.idx_deliveries_notification;
-- DROP INDEX IF EXISTS public.idx_deliveries_approval_request;
-- DROP INDEX IF EXISTS public.uq_deliveries_org_idempotency;
-- DROP INDEX IF EXISTS public.idx_deliveries_processing_attempt_started;
-- DROP INDEX IF EXISTS public.idx_deliveries_retrying_next_attempt;
-- DROP INDEX IF EXISTS public.idx_deliveries_queued_next_attempt;
-- DROP INDEX IF EXISTS public.idx_deliveries_org_recipient_status;
-- DROP INDEX IF EXISTS public.idx_deliveries_org_created;
-- DROP INDEX IF EXISTS public.idx_deliveries_org_status;
-- DROP TABLE IF EXISTS public.delivery_events;
-- DROP TABLE IF EXISTS public.deliveries;
-- DROP TYPE IF EXISTS public.delivery_event_type;
-- DROP TYPE IF EXISTS public.delivery_status;
-- DROP TYPE IF EXISTS public.delivery_channel;
-- =====================================================================
