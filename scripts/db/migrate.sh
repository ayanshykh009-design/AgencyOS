#!/usr/bin/env bash
# Apply database migrations.
# Local dev uses Alembic (backend/); production uses SQL migrations (database/).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT/backend"
alembic upgrade head
