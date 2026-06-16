#!/usr/bin/env bash
#
# Wait for the platform API /cluster-info endpoint to respond.
# Use after starting port-forward so tests don't run before the API is ready.
#
# Usage:
#   wait_for_api.sh [URL] [timeout_seconds]
# Default URL: http://localhost:8080/cluster-info
# Default timeout: 60
#
set -e

URL="${1:-http://localhost:8080/cluster-info}"
TIMEOUT="${2:-60}"

echo "Waiting for API at ${URL} (timeout ${TIMEOUT}s)..."
for i in $(seq 1 "$TIMEOUT"); do
  if curl -sf "$URL" >/dev/null; then
    echo "API ready after ${i}s"
    exit 0
  fi
  sleep 1
done

echo "API not ready after ${TIMEOUT}s"
exit 1
