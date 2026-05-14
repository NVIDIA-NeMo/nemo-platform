#!/usr/bin/env bash
set -euo pipefail
# There is no safe automatic type fix; rerun the lint so remaining issues are visible.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${CI_PROJECT_DIR:-$(cd "${SCRIPT_DIR}/../.." && pwd)}"
cd "${PROJECT_ROOT}" || exit 1

bash tools/lint/lint-python-types.sh || {
  echo "No automatic fix is available for Python type errors."
  exit 1
}
