#!/usr/bin/env bash
set -euo pipefail
# Apply Python formatting and ruff auto-fixes.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${CI_PROJECT_DIR:-$(cd "${SCRIPT_DIR}/../.." && pwd)}"
cd "${PROJECT_ROOT}" || exit 1

uv run ruff check --fix
uv run ruff format
