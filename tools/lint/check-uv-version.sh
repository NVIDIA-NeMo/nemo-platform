#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

_flox_ver="$(yq '.install.uv.version' tools/python/.flox/env/manifest.toml)"

if [[ ! "${_flox_ver}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  printf "Flox must install an exact uv version, found: %s\n" "${_flox_ver}" >&2
  exit 1
fi

while IFS= read -r _workflow; do
  _ci_ver="$(yq '.env.UV_VERSION' "${_workflow}")"

  if [[ "${_ci_ver}" != "${_flox_ver}" ]]; then
    printf "CI and Flox uv versions differ:\n\n" >&2
    printf "workflow flox-env\n%s %s\n" "${_workflow}:${_ci_ver}" "${_flox_ver}" | column -t >&2
    exit 1
  fi
done < <(rg -l 'astral-sh/setup-uv' .github/workflows)
