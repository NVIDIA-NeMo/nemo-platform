#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

# Prepare the *current* git worktree for Studio web/ development:
#   - Copy any missing .env.*.local files from the main worktree across all
#     web/packages/*/env/ directories.
#   - Run pnpm install --frozen-lockfile in web/ so every workspace package
#     has its node_modules.
#
# Worktree creation itself is handled by external tooling (Claude Code's
# --worktree, Cursor, git worktree add, etc.). This script bails if run from
# the main checkout.

CURRENT_WORKTREE="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$CURRENT_WORKTREE" ]]; then
  echo "Error: not inside a git repository"
  exit 1
fi

MAIN_WORKTREE="$(git worktree list --porcelain | head -1 | sed 's/^worktree //')"
if [[ -z "$MAIN_WORKTREE" ]]; then
  echo "Error: could not detect main worktree"
  exit 1
fi

if [[ "$CURRENT_WORKTREE" == "$MAIN_WORKTREE" ]]; then
  echo "Error: you're in the main worktree. Create a linked worktree first"
  echo "       (e.g. \`git worktree add <path>\` or your tool's worktree command)"
  echo "       and run this script from inside it."
  exit 1
fi

echo "Main worktree:    $MAIN_WORKTREE"
echo "Current worktree: $CURRENT_WORKTREE"
echo

# Copy missing .env.*.local files across every web/packages/*/env/ dir that
# exists in the CURRENT worktree. Stale env dirs in main (for packages that no
# longer exist here) are ignored.

copied=0
skipped=0

shopt -s nullglob
for src_env_dir in "$MAIN_WORKTREE"/web/packages/*/env; do
  relative="${src_env_dir#"$MAIN_WORKTREE/"}"
  target_env_dir="$CURRENT_WORKTREE/$relative"

  # Only touch packages that actually exist in the current worktree.
  if [[ ! -d "$target_env_dir" ]]; then
    continue
  fi

  for src_file in "$src_env_dir"/.env.*.local; do
    [[ -f "$src_file" ]] || continue
    filename="$(basename "$src_file")"
    target_file="$target_env_dir/$filename"

    if [[ -f "$target_file" ]]; then
      echo "  skip: $relative/$filename (already exists)"
      skipped=$((skipped + 1))
    else
      cp "$src_file" "$target_file"
      echo "  copy: $relative/$filename"
      copied=$((copied + 1))
    fi
  done
done
shopt -u nullglob

echo
echo "Env files: $copied copied, $skipped skipped"
echo

# Install node_modules for every workspace package (common, studio, etc.) in
# one shot from web/.
echo "Running pnpm install in $CURRENT_WORKTREE/web/ ..."
cd "$CURRENT_WORKTREE/web"
pnpm install --frozen-lockfile
echo
echo "Done. Copy this to start Studio:"
echo
echo "  cd $CURRENT_WORKTREE/web && pnpm dev"
