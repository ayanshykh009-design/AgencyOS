#!/bin/sh
# Launch every standalone AgencyOS background worker as a supervised process.
#
# Workers are process-separated by design (fair-drain queues, bounded sweeps).
# In-process job processors (import/research) are driven by the API layer and
# are intentionally NOT launched here.
#
# Usage (inside the backend image): start_workers.sh
set -u

cd /app

WORKERS="agent approval_gate credential delivery execution founder_action intelligence_triage memory retention"

# Forward SIGTERM to every child so `docker stop` shuts workers down cleanly.
trap 'kill -TERM "$@" 2>/dev/null' TERM INT

PIDS=""
for w in $WORKERS; do
  echo "start_workers: launching app.workers.${w}_worker"
  python -m "app.workers.${w}_worker" &
  PIDS="$PIDS $!"
done

wait
