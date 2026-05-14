#!/usr/bin/env bash
set -euo pipefail
# Regenerate OpenAPI specifications.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${CI_PROJECT_DIR:-$(cd "${SCRIPT_DIR}/../.." && pwd)}"
cd "${PROJECT_ROOT}" || exit 1

make refresh-openapi
rm -rf openapicheck
