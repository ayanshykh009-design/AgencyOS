-- Leads / prospects. Normalized dedup keys are GENERATED columns; the
-- org-scoped partial unique indexes below are the duplicate protection.
CREATE TABLE IF NOT EXISTS public.leads (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id    uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  lead_source_id     uuid REFERENCES public.lead_sources (id) ON DELETE SET NULL,
  owner_user_id      uuid REFERENCES public.users (id) ON DELETE SET NULL,
  status             public.lead_status NOT NULL DEFAULT 'new',
  score              integer NOT NULL DEFAULT 0 CHECK (score >= 0 AND score <= 100),
  first_name         text,
  last_name          text,
  company            text,
  position           text,
  location           text,
  linkedin_url       text,
  email              text CHECK (email IS NULL OR email = lower(btrim(email))),
  phone              text,
  whatsapp           text,
  website            text,
  notes              text,
  stage_id           uuid REFERENCES public.pipeline_stages (id) ON DELETE SET NULL,
  close_reason_id    uuid REFERENCES public.close_reasons (id) ON DELETE SET NULL,
  deal_value         numeric(14, 2) CHECK (deal_value IS NULL OR deal_value >= 0),
  won_at             timestamptz,
  lost_at            timestamptz,
  email_normalized   text GENERATED ALWAYS AS (lower(btrim(email))) STORED,
  phone_normalized   text GENERATED ALWAYS AS (coalesce(normalize_phone(phone), normalize_phone(whatsapp))) STORED,
  website_domain     text GENERATED ALWAYS AS (normalize_domain(website)) STORED,
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now(),
  deleted_at         timestamptz
);

-- Org-scoped duplicate protection (NULL-tolerant partial unique indexes).
CREATE UNIQUE INDEX IF NOT EXISTS uq_leads_org_email
  ON public.leads (organization_id, email_normalized)
  WHERE email_normalized IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_leads_org_phone
  ON public.leads (organization_id, phone_normalized)
  WHERE phone_normalized IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_leads_org_website_domain
  ON public.leads (organization_id, website_domain)
  WHERE website_domain IS NOT NULL;

-- Lookups used by the outreach pipeline.
CREATE INDEX IF NOT EXISTS idx_leads_org_status ON public.leads (organization_id, status);
CREATE INDEX IF NOT EXISTS idx_leads_org_owner ON public.leads (organization_id, owner_user_id);
CREATE INDEX IF NOT EXISTS idx_leads_org_source ON public.leads (organization_id, lead_source_id);
CREATE INDEX IF NOT EXISTS idx_leads_org_updated ON public.leads (organization_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_leads_org_stage ON public.leads (organization_id, stage_id);
CREATE INDEX IF NOT EXISTS idx_leads_org_close_reason
  ON public.leads (organization_id, close_reason_id);
CREATE INDEX IF NOT EXISTS idx_leads_org_active ON public.leads (organization_id)
  WHERE deleted_at IS NULL;

-- Search acceleration (migration 0016): pg_trgm GIN indexes for the
-- substring (ILIKE '%query%') searches used by LeadRepository.search / count.
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX IF NOT EXISTS idx_leads_first_name_trgm
  ON public.leads USING gin (first_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_leads_last_name_trgm
  ON public.leads USING gin (last_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_leads_company_trgm
  ON public.leads USING gin (company gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_leads_email_trgm
  ON public.leads USING gin (email gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_leads_position_trgm
  ON public.leads USING gin (position gin_trgm_ops);

DROP TRIGGER IF EXISTS trg_leads_updated_at ON public.leads;
CREATE TRIGGER trg_leads_updated_at
  BEFORE UPDATE ON public.leads
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
