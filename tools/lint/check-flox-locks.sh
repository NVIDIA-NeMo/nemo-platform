#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

root_lock=".flox/env/manifest.lock"

canonical_manifest() {
  yq -o=json '.options = (.options // {}) | sort_keys(..)' "$1"
}

canonical_composer() {
  yq -o=json '.compose.composer | .options = (.options // {}) | sort_keys(..)' "${root_lock}"
}

canonical_include() {
  local environment_dir="$1"
  yq -o=json "(.compose.include[] | select(.descriptor.dir == \"${environment_dir}\") | .manifest) | .options = (.options // {}) | sort_keys(..)" "${root_lock}"
}

if [[ ! -f "${root_lock}" ]]; then
  echo "Missing ${root_lock}. Run: flox include upgrade" >&2
  exit 1
fi

if [[ "$(canonical_manifest .flox/env/manifest.toml)" != "$(canonical_composer)" ]]; then
  echo "Root Flox manifest is not reflected in ${root_lock}. Run: flox include upgrade" >&2
  exit 1
fi

while IFS= read -r environment_dir; do
  environment_manifest="${environment_dir}/.flox/env/manifest.toml"
  environment_lock="${environment_dir}/.flox/env/manifest.lock"

  if [[ ! -f "${environment_lock}" ]]; then
    echo "Missing ${environment_lock}. Run: flox upgrade --dir ${environment_dir}" >&2
    exit 1
  fi

  if [[ "$(canonical_manifest "${environment_manifest}")" != "$(canonical_manifest "${environment_lock}" | yq -o=json '.manifest')" ]]; then
    echo "${environment_manifest} is not reflected in ${environment_lock}. Run: flox upgrade --dir ${environment_dir}" >&2
    exit 1
  fi

  if [[ "$(canonical_manifest "${environment_lock}" | yq -o=json '.manifest')" != "$(canonical_include "${environment_dir}")" ]]; then
    echo "${environment_lock} is not reflected in ${root_lock}. Run: flox include upgrade" >&2
    exit 1
  fi
done < <(yq -r '.include.environments[].dir' .flox/env/manifest.toml)
