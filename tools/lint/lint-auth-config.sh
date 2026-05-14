#!/usr/bin/env bash
set -euo pipefail
# Verify auth static config and OpenAPI are in sync.
uv run python services/core/auth/scripts/auth-tools.py check || {
  echo "Run 'tools/lint/lint-fix-auth-config.sh' to update auth config and generated auth docs."
  exit 1
}
