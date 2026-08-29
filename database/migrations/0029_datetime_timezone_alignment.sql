-- =====================================================================
-- 0029_datetime_timezone_alignment.sql
-- BASELINE-DB-005: align timestamp columns of the auth/approval/team-invite
-- flows with the canonical timezone-aware UTC convention (every other
-- timestamp column in the schema is timestamptz). The ORM previously inferred
-- naive DateTime for these columns, which made SQLAlchemy read the timestamptz
-- column back as a naive datetime and triggered
--   asyncpg.exceptions.DataError: can't subtract offset-naive and offset-aware
-- datetimes
-- on token/invite/approval lifetime arithmetic (e.g. team_service
-- `invite.expires_at <= utcnow()` and approval_service `now > request.expires_at`).
--
-- Idempotent: only alters columns currently stored WITHOUT time zone. If a
-- column is already timestamptz the ALTER is skipped (safe no-op), so this
-- migration can be replayed without error and is a no-op on databases that
-- already applied the corrected type.
-- =====================================================================

DO $$
DECLARE
  col record;
BEGIN
  FOR col IN
    SELECT * FROM (VALUES
      ('refresh_tokens', 'expires_at'),
      ('refresh_tokens', 'created_at'),
      ('refresh_tokens', 'revoked_at'),
      ('approval_requests', 'expires_at'),
      ('approval_requests', 'decided_at'),
      ('approval_requests', 'gate_handled_at'),
      ('team_invites', 'expires_at'),
      ('team_invites', 'accepted_at'),
      ('team_invites', 'revoked_at')
    ) AS t(tbl, col)
  LOOP
    IF (
      SELECT data_type
      FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = col.tbl
        AND column_name = col.col
    ) = 'timestamp without time zone' THEN
      EXECUTE format(
        'ALTER TABLE public.%I ALTER COLUMN %I TYPE timestamptz USING %I AT TIME ZONE ''UTC''',
        col.tbl, col.col, col.col
      );
    END IF;
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
--     SELECT * FROM (VALUES
--       ('refresh_tokens', 'expires_at'),
--       ('refresh_tokens', 'created_at'),
--       ('refresh_tokens', 'revoked_at'),
--       ('approval_requests', 'expires_at'),
--       ('approval_requests', 'decided_at'),
--       ('approval_requests', 'gate_handled_at'),
--       ('team_invites', 'expires_at'),
--       ('team_invites', 'accepted_at'),
--       ('team_invites', 'revoked_at')
--     ) AS t(tbl, col)
--   LOOP
--     IF (
--       SELECT data_type
--       FROM information_schema.columns
--       WHERE table_schema = 'public'
--         AND table_name = col.tbl
--         AND column_name = col.col
--     ) = 'timestamp with time zone' THEN
--       EXECUTE format(
--         'ALTER TABLE public.%I ALTER COLUMN %I TYPE timestamp',
--         col.tbl, col.col
--       );
--     END IF;
--   END LOOP;
-- END $$;
-- =====================================================================
