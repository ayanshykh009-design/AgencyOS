-- Phase M6: Founder Communication & Delivery Layer enum types.
-- Canonical reference: ../migrations/enums/ (the migration materializes them).
CREATE TYPE public.delivery_channel AS ENUM (
  'dashboard', 'email', 'whatsapp', 'push'
);

CREATE TYPE public.delivery_status AS ENUM (
  'queued', 'processing', 'delivered', 'retrying', 'failed', 'cancelled'
);

CREATE TYPE public.delivery_event_type AS ENUM (
  'queued', 'claimed', 'provider_dispatched', 'provider_returned',
  'delivered', 'retrying', 'failed', 'cancelled', 'timed_out',
  'recovery_guard', 'superseded'
);
