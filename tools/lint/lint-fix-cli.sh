#!/usr/bin/env bash
set -euo pipefail
# Regenerate CLI commands, vendored CLI package metadata, and CLI reference docs.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${CI_PROJECT_DIR:-$(cd "${SCRIPT_DIR}/../.." && pwd)}"
cd "${PROJECT_ROOT}" || exit 1

make update-cli
