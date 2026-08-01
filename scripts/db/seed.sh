#!/usr/bin/env bash
# Apply seed data (idempotent).
# Adjust PSQL_TARGET to point at the right database.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PSQL_TARGET="${PSQL_TARGET:-postgresql://agencyos:change-me@localhost:5432/agencyos}"

for seed in "$ROOT"/database/seeds/*.sql; do
  echo "applying $seed"
  psql "$PSQL_TARGET" -v ON_ERROR_STOP=1 -f "$seed"
done
