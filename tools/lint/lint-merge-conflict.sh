#!/usr/bin/env bash
set -euo pipefail
uv run pre-commit run check-merge-conflict || {
  echo "Run 'tools/lint/lint-fix-merge-conflict.sh' after manually resolving conflict markers."
  exit 1
}
