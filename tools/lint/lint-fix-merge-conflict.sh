#!/usr/bin/env bash
set -euo pipefail
# There is no safe automatic edit for merge conflict markers; rerun the lint.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${CI_PROJECT_DIR:-$(cd "${SCRIPT_DIR}/../.." && pwd)}"
cd "${PROJECT_ROOT}" || exit 1

bash tools/lint/lint-merge-conflict.sh || {
  echo "No automatic fix is available for merge conflict markers."
  exit 1
}
