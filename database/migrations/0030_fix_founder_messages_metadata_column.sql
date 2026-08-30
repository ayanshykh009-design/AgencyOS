-- Fix founder_messages metadata column name.
--
-- Migration 0026 created the column as "metadata_" but the ORM model
-- (app.models.founder_message.FounderMessage) maps the "metadata_" attribute
-- to the database column "metadata". That mismatch made every insert/select
-- against founder_messages fail with "column metadata does not exist".
--
-- Non-destructive rename so both fresh installs and already-applied databases
-- converge on the correct column name.
ALTER TABLE IF EXISTS public.founder_messages
  RENAME COLUMN metadata_ TO metadata;
