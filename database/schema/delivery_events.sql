-- delivery_events: immutable per-delivery timeline (Phase M6)
-- Rows are never updated or deleted; no updated_at, no write policies.
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
