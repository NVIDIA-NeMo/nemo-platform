#!/usr/bin/env bash
set -euo pipefail
# Verify third-party licenses are up to date.
make check-licenses || {
  echo "Run 'tools/lint/lint-fix-licenses.sh' to update license files."
  exit 1
}
# This only runs if the diff doesn't exit early
git restore third_party
