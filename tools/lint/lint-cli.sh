#!/usr/bin/env bash
set -euo pipefail
# Verify CLI is up to date (make update-cli leaves no uncommitted changes).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${CI_PROJECT_DIR:-$(cd "${SCRIPT_DIR}/../.." && pwd)}"
cd "${PROJECT_ROOT}"

make update-cli
git add "${PROJECT_ROOT}/sdk/python/"
git diff --cached --exit-code "${PROJECT_ROOT}/sdk/python/" > "${PROJECT_ROOT}/diff.txt" || {
  echo "Run 'tools/lint/lint-fix-cli.sh' to update the CLI."
  exit 1
}
