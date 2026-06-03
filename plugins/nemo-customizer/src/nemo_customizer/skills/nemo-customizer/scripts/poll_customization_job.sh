#!/usr/bin/env bash
# Poll customization job until top-level status is terminal.
# Usage: poll_customization_job.sh <plugin>-<job-id> [interval_seconds]
# Requires: NEMO_BASE_URL or NMP_BASE_URL, run from nemo-platform root with `uv run`.
# Exit 0 on completed; exit 1 on error, cancelled, or get-status failure.

set -euo pipefail

JOB="${1:?usage: poll_customization_job.sh <plugin>-<id> [interval_seconds]}"
INTERVAL="${2:-15}"

while true; do
  JSON=$(uv run nemo jobs get-status "$JOB" 2>/dev/null) || {
    echo "get-status failed for $JOB" >&2
    exit 1
  }
  read -r STATUS PHASE <<<"$(printf '%s' "$JSON" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d['status'], d.get('status_details', {}).get('phase', ''))
")"
  echo "$(date +%H:%M:%S) status=$STATUS phase=$PHASE"
  case "$STATUS" in
    completed)
      printf '%s\n' "$JSON" | python3 -m json.tool
      exit 0
      ;;
    error|cancelled)
      printf '%s\n' "$JSON" | python3 -m json.tool >&2
      exit 1
      ;;
  esac
  sleep "$INTERVAL"
done
