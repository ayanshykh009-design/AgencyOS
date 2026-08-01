-- Provider token/request accounting. No credentials are stored anywhere
-- in the schema — `provider` is only a label (e.g. 'openai', 'smtp').
CREATE TABLE IF NOT EXISTS public.provider_usage (
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

CREATE INDEX IF NOT EXISTS idx_provider_usage_org_date
  ON public.provider_usage (organization_id, usage_date DESC);

DROP TRIGGER IF EXISTS trg_provider_usage_updated_at ON public.provider_usage;
CREATE TRIGGER trg_provider_usage_updated_at
  BEFORE UPDATE ON public.provider_usage
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
