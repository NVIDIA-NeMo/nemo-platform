#!/usr/bin/env bash
set -euo pipefail
# Verify config reference doc is up to date.
uv run --frozen generate-config-docs
git diff --exit-code docs/set-up/config-reference.md || {
  echo "Config reference doc is out of date. Run 'tools/lint/lint-fix-config-reference-docs.sh' and commit docs/set-up/config-reference.md."
  exit 1
}
