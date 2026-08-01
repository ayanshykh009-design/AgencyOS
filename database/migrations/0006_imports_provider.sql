-- =====================================================================
-- 0006_imports_provider.sql
-- CSV import pipeline + provider usage accounting: import_jobs,
-- import_row_errors, provider_usage.
-- =====================================================================

-- ---------------------------------------------------------------------
-- import_jobs (CSV import is import-only; Postgres is the source of truth)
-- ---------------------------------------------------------------------
CREATE TABLE public.import_jobs (
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

CREATE INDEX idx_import_jobs_org_status ON public.import_jobs (organization_id, status);
CREATE INDEX idx_import_jobs_org_created ON public.import_jobs (organization_id, created_at DESC);

CREATE TRIGGER trg_import_jobs_updated_at
  BEFORE UPDATE ON public.import_jobs
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------
-- import_row_errors (append-only per-row failure log)
-- ---------------------------------------------------------------------
CREATE TABLE public.import_row_errors (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  import_job_id   uuid NOT NULL REFERENCES public.import_jobs (id) ON DELETE CASCADE,
  organization_id uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  row_number      integer NOT NULL CHECK (row_number >= 1),
  error_code      text NOT NULL CHECK (length(btrim(error_code)) > 0),
  error_message   text NOT NULL CHECK (length(btrim(error_message)) > 0),
  raw_row         jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_import_row_errors_job ON public.import_row_errors (import_job_id);

-- ---------------------------------------------------------------------
-- provider_usage (token/request accounting — no credentials stored)
-- ---------------------------------------------------------------------
CREATE TABLE public.provider_usage (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  provider        text NOT NULL CHECK (length(btrim(provider)) > 0),
  feature         text NOT NULL CHECK (length(btrim(feature)) > 0),
  usage_date      date NOT NULL,
  request_count   integer NOT NULL DEFAULT 0 CHECK (request_count >= 0),
  input_tokens    integer NOT NULL DEFAULT 0 CHECK (input_tokens >= 0),
  output_tokens   integer NOT NULL DEFAULT 0 CHECK (output_tokens >= 0),
  cost_usd        numeric(12, 6) NOT NULL DEFAULT 0 CHECK (cost_usd >= 0),
  metadata        jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_provider_usage_daily UNIQUE (organization_id, provider, feature, usage_date)
);

CREATE INDEX idx_provider_usage_org_date
  ON public.provider_usage (organization_id, usage_date DESC);

CREATE TRIGGER trg_provider_usage_updated_at
  BEFORE UPDATE ON public.provider_usage
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------
ALTER TABLE public.import_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.import_row_errors ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.provider_usage ENABLE ROW LEVEL SECURITY;

-- =====================================================================
-- ROLLBACK
-- =====================================================================
-- DROP TABLE IF EXISTS public.provider_usage;
-- DROP TABLE IF EXISTS public.import_row_errors;
-- DROP TABLE IF EXISTS public.import_jobs;
-- =====================================================================
