#!/usr/bin/env bash
# Poll automodel job until top-level status is terminal.
# Usage: poll_automodel_job.sh automodel-<job-id> [interval_seconds]
# Requires: NEMO_BASE_URL or NMP_BASE_URL, run from nemo-platform root with `uv run`.

set -euo pipefail

JOB="${1:?usage: poll_automodel_job.sh automodel-<id> [interval_seconds]}"
INTERVAL="${2:-90}"

while true; do
  JSON=$(uv run nemo jobs get-status "$JOB" 2>/dev/null) || {
    echo "get-status failed for $JOB" >&2
    exit 1
  }
  STATUS=$(printf '%s' "$JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
  PHASE=$(printf '%s' "$JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status_details',{}).get('phase',''))")
  echo "$(date +%H:%M:%S) status=$STATUS phase=$PHASE"
  case "$STATUS" in
    completed|failed|cancelled)
      printf '%s\n' "$JSON" | python3 -m json.tool
      exit 0
      ;;
  esac
  sleep "$INTERVAL"
done
