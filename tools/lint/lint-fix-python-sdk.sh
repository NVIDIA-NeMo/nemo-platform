#!/usr/bin/env bash
set -euo pipefail
# Sync the Python SDK with the current OpenAPI spec when it is out of date.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${CI_PROJECT_DIR:-$(cd "${SCRIPT_DIR}/../.." && pwd)}"
cd "${PROJECT_ROOT}" || exit 1

OUTPUT_DIR="${TMPDIR:-/tmp}/nmp-sdk-lint"
uv run --frozen nemo-platform-sdk-tools is-up-to-date --output-dir "${OUTPUT_DIR}" || make stainless
