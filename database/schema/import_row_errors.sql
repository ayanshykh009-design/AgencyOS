-- Append-only per-row failures from import jobs.
CREATE TABLE IF NOT EXISTS public.import_row_errors (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  import_job_id   uuid NOT NULL REFERENCES public.import_jobs (id) ON DELETE CASCADE,
  organization_id uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  row_number      integer NOT NULL CHECK (row_number >= 1),
  error_code      text NOT NULL CHECK (length(btrim(error_code)) > 0),
  error_message   text NOT NULL CHECK (length(btrim(error_message)) > 0),
  raw_row         jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_import_row_errors_job ON public.import_row_errors (import_job_id);
