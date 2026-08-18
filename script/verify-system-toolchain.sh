#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

mode="${1:-python}"
if [[ "${mode}" != "python" && "${mode}" != "web" ]]; then
  echo "Usage: $0 [python|web]" >&2
  exit 2
fi

version_at_least() {
  local current="$1"
  local minimum="$2"
  local current_part
  local minimum_part
  local index
  local -a current_parts minimum_parts

  IFS=. read -r -a current_parts <<<"${current}"
  IFS=. read -r -a minimum_parts <<<"${minimum}"

  for index in 0 1 2; do
    current_part="${current_parts[index]:-0}"
    minimum_part="${minimum_parts[index]:-0}"
    if ((10#${current_part} > 10#${minimum_part})); then
      return 0
    fi
    if ((10#${current_part} < 10#${minimum_part})); then
      return 1
    fi
  done
}

if ! command -v uv >/dev/null 2>&1; then
  echo "TOOLCHAIN=system requires uv on PATH." >&2
  exit 1
fi

uv_minimum="$(sed -n 's/^required-version = ">=\([^"]*\)"/\1/p' pyproject.toml)"
uv_current="$(uv --version | awk '{print $2}')"
if [[ -z "${uv_minimum}" ]] || ! version_at_least "${uv_current}" "${uv_minimum}"; then
  echo "TOOLCHAIN=system requires uv >=${uv_minimum:-the project minimum}; found ${uv_current}." >&2
  exit 1
fi

if [[ "${mode}" = "python" ]]; then
  exit 0
fi

for tool in node pnpm; do
  if ! command -v "${tool}" >/dev/null 2>&1; then
    echo "TOOLCHAIN=system requires ${tool} on PATH for Studio work." >&2
    exit 1
  fi
done

node_required="$(tr -d '[:space:]' < .nvmrc)"
node_current="$(node --version | sed 's/^v//')"
pnpm_required="$(sed -n 's/.*"packageManager": "pnpm@\([^"]*\)".*/\1/p' web/package.json)"
pnpm_current="$(pnpm --version)"

if [[ "${node_current}" != "${node_required}" ]]; then
  echo "TOOLCHAIN=system requires Node.js ${node_required}; found ${node_current}." >&2
  exit 1
fi

if [[ "${pnpm_current}" != "${pnpm_required}" ]]; then
  echo "TOOLCHAIN=system requires pnpm ${pnpm_required}; found ${pnpm_current}." >&2
  exit 1
fi
