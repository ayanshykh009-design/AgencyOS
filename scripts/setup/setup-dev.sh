#!/usr/bin/env bash
# Bootstrap the AgencyOS workspace: copy env templates and ensure storage dirs.
# Idempotent — safe to re-run. Usage: scripts/setup/setup-dev.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

copy_if_missing() {
  local src="$1" dst="$2"
  if [[ ! -f "$dst" ]]; then
    cp "$src" "$dst"
    echo "created $dst"
  else
    echo "exists  $dst"
  fi
}

copy_if_missing "$ROOT/.env.example"            "$ROOT/.env"
copy_if_missing "$ROOT/backend/.env.example"    "$ROOT/backend/.env"
copy_if_missing "$ROOT/frontend/.env.example"   "$ROOT/frontend/.env.local"

for dir in storage/uploads storage/exports storage/logs storage/backups; do
  mkdir -p "$ROOT/$dir"
  touch "$ROOT/$dir/.gitkeep"
done

echo "AgencyOS workspace ready. Edit the created .env files with real values."
