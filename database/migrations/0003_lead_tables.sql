-- =====================================================================
-- 0003_lead_tables.sql
-- Lead sourcing and enrichment: lead_sources, leads, lead_research.
--
-- Duplicate protection strategy:
--   * normalized columns are GENERATED ALWAYS (deterministic, DB-enforced)
--   * partial UNIQUE indexes make dedup org-scoped and NULL-tolerant
--   * phone and WhatsApp share one normalized channel (phone_normalized)
-- =====================================================================

-- Immutable text normalizers (pure string transforms, safe for generated columns).
CREATE OR REPLACE FUNCTION public.normalize_phone(raw_value text)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT CASE WHEN length(digits) = 0 THEN NULL ELSE digits END
  FROM (SELECT regexp_replace(coalesce(raw_value, ''), '\D', '', 'g') AS digits) AS s
$$;

CREATE OR REPLACE FUNCTION public.normalize_domain(url text)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT NULLIF(lower(btrim(
           regexp_replace(
             regexp_replace(
               regexp_replace(coalesce(url, ''), '^[a-zA-Z][a-zA-Z0-9+.-]*://', ''),
               '/.*$', '', 'g'
             ),
             '^www\.', '', 'g'
           ),
           '.'
         )), '')
$$;

-- ---------------------------------------------------------------------
-- lead_sources
-- ---------------------------------------------------------------------
CREATE TABLE public.lead_sources (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  name            text NOT NULL CHECK (length(btrim(name)) > 0),
  channel         public.outreach_channel NOT NULL DEFAULT 'contact_form',
  description     text,
  is_active       boolean NOT NULL DEFAULT true,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_lead_sources_org_name UNIQUE (organization_id, name)
);

CREATE INDEX IF NOT EXISTS idx_lead_sources_org ON public.lead_sources (organization_id);

DROP TRIGGER IF EXISTS trg_lead_sources_updated_at ON public.lead_sources;

CREATE TRIGGER trg_lead_sources_updated_at
  BEFORE UPDATE ON public.lead_sources
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------
-- leads
-- ---------------------------------------------------------------------
CREATE TABLE public.leads (
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
  -- Normalized, generated columns (dedup keys — do not write these directly).
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
CREATE INDEX IF NOT EXISTS idx_leads_org_active ON public.leads (organization_id)
  WHERE deleted_at IS NULL;

DROP TRIGGER IF EXISTS trg_leads_updated_at ON public.leads;

CREATE TRIGGER trg_leads_updated_at
  BEFORE UPDATE ON public.leads
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------
-- lead_research (one research row per lead)
-- ---------------------------------------------------------------------
CREATE TABLE public.lead_research (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  lead_id          uuid NOT NULL REFERENCES public.leads (id) ON DELETE CASCADE,
  organization_id  uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  status           text NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending', 'in_progress', 'completed', 'failed')),
  company_overview text,
  pain_points      jsonb NOT NULL DEFAULT '[]'::jsonb,
  tech_stack       jsonb NOT NULL DEFAULT '[]'::jsonb,
  recent_news      jsonb NOT NULL DEFAULT '[]'::jsonb,
  linkedin_summary text,
  icp_match_score  integer CHECK (icp_match_score IS NULL OR (icp_match_score >= 0 AND icp_match_score <= 100)),
  raw_data         jsonb NOT NULL DEFAULT '{}'::jsonb,
  research_source  text,
  researched_at    timestamptz,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_lead_research_lead UNIQUE (lead_id)
);

CREATE INDEX IF NOT EXISTS idx_lead_research_org ON public.lead_research (organization_id);

DROP TRIGGER IF EXISTS trg_lead_research_updated_at ON public.lead_research;

CREATE TRIGGER trg_lead_research_updated_at
  BEFORE UPDATE ON public.lead_research
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------
ALTER TABLE public.lead_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.leads ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.lead_research ENABLE ROW LEVEL SECURITY;

-- =====================================================================
-- ROLLBACK
-- =====================================================================
-- DROP TABLE IF EXISTS public.lead_research;
-- DROP TABLE IF EXISTS public.leads;
-- DROP TABLE IF EXISTS public.lead_sources;
-- DROP FUNCTION IF EXISTS public.normalize_domain(text);
-- DROP FUNCTION IF EXISTS public.normalize_phone(text);
-- =====================================================================
