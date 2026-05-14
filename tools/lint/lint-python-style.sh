#!/usr/bin/env bash
set -euo pipefail
# Check Python style with ruff (lint and format).
# Uses the ruff version pinned in pyproject.toml dev dependencies.
status=0
uv run ruff check || status=1
uv run ruff format --check || status=1
if [[ ${status} -ne 0 ]]; then
  echo "Run 'tools/lint/lint-fix-python-style.sh' to apply Python style fixes."
  exit 1
fi
