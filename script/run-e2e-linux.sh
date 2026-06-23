#!/usr/bin/env bash
set -euo pipefail

# Run NeMo Platform E2E tests inside a local Linux container to compare
# behavior with GitHub Actions' ubuntu-latest environment.
#
# Examples:
#   script/run-e2e-linux.sh
#   script/run-e2e-linux.sh e2e/test_jobs_auth.py -vv -s --run-e2e
#
# Requirements:
# - local Docker daemon
# - outbound network access from the container for uv package sync

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${NMP_E2E_LINUX_IMAGE:-python:3.13-slim-bookworm}"
CONTAINER_NAME="nmp-e2e-linux-$(date +%s)"
PYTEST_ARGS=("$@")

if [ "${#PYTEST_ARGS[@]}" -eq 0 ]; then
  PYTEST_ARGS=(e2e/test_jobs_auth.py -vv -s --run-e2e)
fi

docker run --rm --name "${CONTAINER_NAME}" \
  -e _TYPER_FORCE_DISABLE_TERMINAL=1 \
  -e E2E_SERVICES_LOG_DIR=/tmp/e2e-services-logs \
  -e UV_PROJECT_ENVIRONMENT=/tmp/nmp-e2e-linux-venv \
  -e NGC_API_KEY="${NGC_API_KEY:-not-set}" \
  -e HF_TOKEN="${HF_TOKEN:-}" \
  -v "${ROOT_DIR}:/workspace" \
  -w /workspace \
  "${IMAGE}" \
  bash -lc '
    set -euo pipefail
    apt-get update
    apt-get install -y --no-install-recommends curl git build-essential
    rm -rf /var/lib/apt/lists/*
    python -m pip install --no-cache-dir "uv>=0.9.14,<0.10.0"
    uv sync --frozen --all-packages
    uv run --frozen pytest '"$(printf '%q ' "${PYTEST_ARGS[@]}")"'
  '
