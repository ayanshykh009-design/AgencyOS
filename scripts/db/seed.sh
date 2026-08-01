#!/usr/bin/env bash
# Apply seed data (idempotent, fixed UUIDs). Requires migrations to be
# applied first (scripts/db/migrate.sh).
# Usage: scripts/db/seed.sh [target_psql_url]  |  env PSQL_TARGET=...
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PSQL_TARGET="${PSQL_TARGET:-postgresql://agencyos:change-me@localhost:5432/agencyos}"

if ! command -v psql >/dev/null 2>&1; then
  echo "ERROR: psql not found. Install PostgreSQL client or run the docker compose postgres service." >&2
  exit 1
fi

for seed in "$ROOT"/database/seeds/[0-9][0-9]_*.sql; do
  [ -e "$seed" ] || { echo "No seed files found in database/seeds/"; exit 0; }
  echo "applying $(basename "$seed")"
  psql "$PSQL_TARGET" -v ON_ERROR_STOP=1 -1 -f "$seed"
done
