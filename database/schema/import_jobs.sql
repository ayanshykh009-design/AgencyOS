-- CSV import job (import-only; PostgreSQL remains the source of truth).
CREATE TABLE IF NOT EXISTS public.import_jobs (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id    uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  created_by_user_id uuid NOT NULL REFERENCES public.users (id) ON DELETE RESTRICT,
  lead_source_id     uuid REFERENCES public.lead_sources (id) ON DELETE SET NULL,
  status             public.import_status NOT NULL DEFAULT 'pending',
  file_name          text NOT NULL CHECK (length(btrim(file_name)) > 0),
  file_size_bytes    bigint NOT NULL DEFAULT 0 CHECK (file_size_bytes >= 0),
  total_rows         integer NOT NULL DEFAULT 0 CHECK (total_rows >= 0),
  processed_rows     integer NOT NULL DEFAULT 0 CHECK (processed_rows >= 0),
  failed_rows        integer NOT NULL DEFAULT 0 CHECK (failed_rows >= 0),
  metadata           jsonb NOT NULL DEFAULT '{}'::jsonb,
  started_at         timestamptz,
  finished_at        timestamptz,
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT chk_import_jobs_counts
    CHECK (processed_rows <= total_rows AND failed_rows <= total_rows)
);

CREATE INDEX IF NOT EXISTS idx_import_jobs_org_status ON public.import_jobs (organization_id, status);
CREATE INDEX IF NOT EXISTS idx_import_jobs_org_created ON public.import_jobs (organization_id, created_at DESC);

DROP TRIGGER IF EXISTS trg_import_jobs_updated_at ON public.import_jobs;
CREATE TRIGGER trg_import_jobs_updated_at
  BEFORE UPDATE ON public.import_jobs
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
