#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# Post-edit hook for Studio files
# Runs ESLint and Prettier on edited files under web/.
# Prettier defers to .prettierignore for exclusions; ESLint defers to eslint.config.js.

set -euo pipefail

# Ensure nvm-managed Node is available
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

# Exit if no file path
if [[ -z "$FILE_PATH" ]]; then
  exit 0
fi

# Resolve studio root — works whether launched from repo root or web/
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STUDIO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Only process files under web/
case "$FILE_PATH" in
  "$STUDIO_DIR"/*) ;;
  *) exit 0 ;;
esac

cd "$STUDIO_DIR"

# Run tools based on extension — order matches lint-staged: ESLint first, then Prettier
case "$FILE_PATH" in
  *.ts|*.tsx|*.js|*.jsx)
    pnpm exec eslint --no-warn-ignored --max-warnings 0 "$FILE_PATH"
    pnpm exec prettier --write "$FILE_PATH"
    ;;
  *.json|*.yaml|*.yml|*.md)
    pnpm exec prettier --write "$FILE_PATH"
    ;;
esac

exit 0
