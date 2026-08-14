#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# .claude/hooks/nvm-on-cd.sh
# Switches Node version via nvm when cd'ing into a directory with .nvmrc.
# Writes the resulting PATH to CLAUDE_ENV_FILE so it persists across Bash calls.

INPUT=$(cat)
NEW_CWD=$(echo "$INPUT" | jq -r '.new_cwd' 2>/dev/null)

if [ -z "$NEW_CWD" ] || [ "$NEW_CWD" = "null" ]; then
  exit 0
fi

# Walk up from NEW_CWD to find the nearest .nvmrc
SEARCH="$NEW_CWD"
NVMRC=""
while [ "$SEARCH" != "/" ]; do
  if [ -f "$SEARCH/.nvmrc" ]; then
    NVMRC="$SEARCH/.nvmrc"
    break
  fi
  SEARCH=$(dirname "$SEARCH")
done

if [ -z "$NVMRC" ]; then
  exit 0
fi

# Honor existing NVM_DIR, fall back to ~/.nvm
NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
export NVM_DIR

if [ ! -s "$NVM_DIR/nvm.sh" ]; then
  exit 0
fi

source "$NVM_DIR/nvm.sh" --no-use

WANTED=$(cat "$NVMRC")
NODE_VERSION=$(nvm version "$WANTED" 2>/dev/null)

if [ "$NODE_VERSION" = "N/A" ]; then
  exit 0
fi

NVM_BIN="$NVM_DIR/versions/node/$NODE_VERSION/bin"

if [ ! -d "$NVM_BIN" ]; then
  exit 0
fi

if [ -n "$CLAUDE_ENV_FILE" ]; then
  # Build a clean PATH: keep entries that aren't nvm-managed node versions
  CLEAN_PATH=""
  IFS=':'
  for entry in $PATH; do
    case "$entry" in
      "$NVM_DIR/versions/node"*) continue ;;
    esac
    if [ -z "$CLEAN_PATH" ]; then
      CLEAN_PATH="$entry"
    else
      CLEAN_PATH="$CLEAN_PATH:$entry"
    fi
  done
  unset IFS

  # Remove any prior PATH exports from the env file, then write the new one.
  # This prevents the file from growing on every cd.
  if [ -f "$CLAUDE_ENV_FILE" ]; then
    grep -v '^export PATH=' "$CLAUDE_ENV_FILE" > "$CLAUDE_ENV_FILE.tmp" 2>/dev/null
    mv "$CLAUDE_ENV_FILE.tmp" "$CLAUDE_ENV_FILE"
  fi
  echo "export PATH=\"$NVM_BIN:$CLEAN_PATH\"" >> "$CLAUDE_ENV_FILE"
fi

exit 0
