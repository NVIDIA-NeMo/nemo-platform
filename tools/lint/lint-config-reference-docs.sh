#!/usr/bin/env bash
set -euo pipefail
# Verify config reference doc is up to date.
uv run --frozen generate-config-docs
git diff --exit-code docs/set-up/config-reference.mdx || {
  echo "Config reference doc is out of date. Run 'uv run generate-config-docs' and commit docs/set-up/config-reference.mdx"
  exit 1
}
