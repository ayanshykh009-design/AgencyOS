#!/usr/bin/env bash
# Apply SQL schema migrations (database/migrations/) in numeric order.
# Applied versions are tracked in public.schema_migrations (idempotent).
#
# Usage:
#   scripts/db/migrate.sh [target_psql_url]
# Defaults to the local dev database. Override with PSQL_TARGET.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PSQL_TARGET="${PSQL_TARGET:-postgresql://agencyos:change-me@localhost:5432/agencyos}"
MIGRATIONS_DIR="$ROOT/database/migrations"

if ! command -v psql >/dev/null 2>&1; then
  echo "ERROR: psql not found. Install PostgreSQL client or run the docker compose postgres service." >&2
  exit 1
fi

psql "$PSQL_TARGET" -v ON_ERROR_STOP=1 -q -c "
CREATE TABLE IF NOT EXISTS public.schema_migrations (
  version    text PRIMARY KEY,
  applied_at timestamptz NOT NULL DEFAULT now()
);"

applied_any=false
for f in "$MIGRATIONS_DIR"/[0-9][0-9][0-9][0-9]_*.sql; do
  [ -e "$f" ] || { echo "No migrations found in $MIGRATIONS_DIR"; exit 0; }
  name="$(basename "$f")"
  already="$(psql "$PSQL_TARGET" -tA -c "SELECT 1 FROM public.schema_migrations WHERE version = '${name}'" | head -n1)"
  if [ "$already" = "1" ]; then
    echo "skip  $name (already applied)"
    continue
  fi
  echo "apply $name"
  psql "$PSQL_TARGET" -v ON_ERROR_STOP=1 -1 -f "$f"
  psql "$PSQL_TARGET" -q -c "INSERT INTO public.schema_migrations (version) VALUES ('${name}');"
  applied_any=true
done

if [ "$applied_any" = false ]; then
  echo "Schema is up to date."
fi
