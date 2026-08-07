-- execution_event_type: labels for the append-only execution timeline.
-- Canonical reference: ../migrations/enums/ (the migration materializes them).
CREATE TYPE public.execution_event_type AS ENUM (
  'queued', 'started', 'adapter_dispatched', 'adapter_returned',
  'step_started', 'step_completed', 'step_failed',
  'retrying', 'succeeded', 'failed', 'cancelled', 'timed_out',
  'timeout_guard'
);
