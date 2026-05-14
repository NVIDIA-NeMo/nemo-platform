#!/usr/bin/env bash
set -euo pipefail
# Verify vendored SDK is in sync (make vendor leaves no uncommitted changes).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${CI_PROJECT_DIR:-$(cd "${SCRIPT_DIR}/../.." && pwd)}"
cd "${PROJECT_ROOT}"
export PATH="$HOME/.local/bin:$PATH"

make vendor
git add "${PROJECT_ROOT}/sdk/python/" "${PROJECT_ROOT}/packages/nemo_platform/pyproject.toml"
git diff --cached --exit-code "${PROJECT_ROOT}/sdk/python/" "${PROJECT_ROOT}/packages/nemo_platform/pyproject.toml" > "${PROJECT_ROOT}/diff.txt" || {
  echo "Run 'tools/lint/lint-fix-sdk-vendored.sh' to sync packages with the SDK and wrapper."
  exit 1
}

make generate-cli-reference-docs
git add "${PROJECT_ROOT}/docs/cli"
git diff --cached --exit-code "${PROJECT_ROOT}/docs/cli" > "${PROJECT_ROOT}/diff.txt" || {
  echo "Run 'tools/lint/lint-fix-sdk-vendored.sh' to sync CLI docs."
  exit 1
}
