-- Shared schema helpers: audit trigger + normalized dedup key functions.
-- These are the canonical definitions; migrations reference them.

CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at = clock_timestamp();
  RETURN NEW;
END;
$$;

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
