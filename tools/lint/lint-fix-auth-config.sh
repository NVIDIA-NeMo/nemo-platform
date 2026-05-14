#!/usr/bin/env bash
set -euo pipefail
# Update auth static config and generated auth permission docs.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${CI_PROJECT_DIR:-$(cd "${SCRIPT_DIR}/../.." && pwd)}"
cd "${PROJECT_ROOT}" || exit 1

uv run python services/core/auth/scripts/auth-tools.py update
uv run python services/core/auth/scripts/auth-tools.py generate-docs
