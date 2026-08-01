#!/usr/bin/env bash
# Verify required env vars are present. Exit non-zero if any are missing.
# Usage: scripts/utils/check-env.sh SECRET_KEY SUPABASE_URL
set -euo pipefail
missing=0
for var in "$@"; do
  if [[ -z "${!var:-}" ]]; then
    echo "missing env var: $var"
    missing=1
  fi
done
if [[ $missing -ne 0 ]]; then
  echo "Aborting: one or more required env vars are missing." >&2
  exit 1
fi
echo "All required env vars present."
