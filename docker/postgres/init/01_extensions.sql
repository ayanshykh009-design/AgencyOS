-- AgencyOS local Postgres init scripts.
-- Executed once on first container start by docker-entrypoint-initdb.d.

-- Core extensions used by the schema.
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
