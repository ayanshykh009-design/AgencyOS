-- =====================================================================
-- 0029_datetime_timezone_alignment.sql
-- BASELINE-DB-005: align every timestamp column with the canonical
-- timezone-aware UTC convention.
--
-- The application always writes UTC-aware datetimes
-- (e.g. `datetime.now(timezone.utc)` / `utcnow()`) into these columns.
-- Any column stored as `timestamp without time zone` therefore triggers
--   asyncpg.exceptions.DataError: can't subtract offset-naive and offset-aware
--   datetimes
-- on insert/update (the DBAPI cannot encode an aware value into a naive
-- column) and returns naive values on read (breaking lifetime arithmetic such
-- as `expires_at <= utcnow()`).
--
-- Fix: convert EVERY `timestamp without time zone` column in the public schema
-- to `timestamptz`, interpreting existing values as UTC. This matches the
-- convention already used by the rest of the schema (created_at/updated_at and
-- the auth/approval/team-invite timestamp columns) and the SQLAlchemy models.
--
-- Idempotent: the conversion only touches columns currently stored WITHOUT
-- time zone, so replaying this migration is a no-op on an already-aligned
-- database.
-- =====================================================================

DO $$
DECLARE
  col record;
BEGIN
  FOR col IN
    SELECT table_name, column_name
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND data_type = 'timestamp without time zone'
      -- bootstrap tables created outside the migration set are timestamptz
      -- already and are simply skipped by the data_type filter above.
  LOOP
    EXECUTE format(
      'ALTER TABLE public.%I ALTER COLUMN %I TYPE timestamptz USING %I AT TIME ZONE ''UTC''',
      col.table_name, col.column_name, col.column_name
    );
  END LOOP;
END $$;

-- =====================================================================
-- ROLLBACK
-- =====================================================================
-- DO $$
-- DECLARE
--   col record;
-- BEGIN
--   FOR col IN
--     SELECT table_name, column_name
--     FROM information_schema.columns
--     WHERE table_schema = 'public'
--       AND data_type = 'timestamp with time zone'
--   LOOP
--     EXECUTE format(
--       'ALTER TABLE public.%I ALTER COLUMN %I TYPE timestamp without time zone',
--       col.table_name, col.column_name
--     );
--   END LOOP;
-- END $$;
-- =====================================================================
