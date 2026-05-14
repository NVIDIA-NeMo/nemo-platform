#!/usr/bin/env bash
set -uo pipefail
# Verify the TypeScript web SDK (web/packages/sdk) is up to date with the OpenAPI spec
# by regenerating and diffing via `pnpm gen:check`. Skips locally when pnpm is absent
# (mirrors the studio-lint-staged pre-commit hook); hard-fails under CI.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${CI_PROJECT_DIR:-$(cd "${SCRIPT_DIR}/../.." && pwd)}"
cd "${PROJECT_ROOT}/web" || exit 1

if ! command -v pnpm >/dev/null 2>&1; then
  if [[ -n "${CI:-}" ]]; then
    echo "pnpm required in CI but not found on PATH" >&2
    exit 1
  fi
  echo "pnpm not installed locally — skipping web SDK check (see web/README.md for setup)"
  exit 0
fi

pnpm gen:check || {
  echo "Run 'tools/lint/lint-fix-web-sdk.sh' to regenerate the web SDK."
  exit 1
}
