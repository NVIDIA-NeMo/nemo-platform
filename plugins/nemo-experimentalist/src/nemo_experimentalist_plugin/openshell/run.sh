#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "usage: $0 PREPARED_INPUT_DIR OUTPUT_DIR POLICY_PATH" >&2
  exit 2
fi
if ! command -v openshell >/dev/null 2>&1; then
  echo "openshell CLI is required" >&2
  exit 127
fi

input_dir="$(cd "$1" && pwd)"
remote_input="/sandbox/input/$(basename "$input_dir")"
output_dir="$2"
policy_path="$3"
image="${NEMO_EXPERIMENTALIST_IMAGE:-local/nmp-experimentalist:local}"
sandbox_name="${NEMO_EXPERIMENTALIST_SANDBOX_NAME:-nemo-exp-$$}"
platform_url="${NMP_BASE_URL:-http://host.openshell.internal:8080}"
bridge_url="${NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_URL:-http://host.openshell.internal:8765}"
bridge_provider="${NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_PROVIDER:-nemo-experimentalist-harbor-bridge}"
policy_mode="${NEMO_EXPERIMENTALIST_POLICY_MODE:-strict}"

if (( ${#sandbox_name} > 19 )); then
  echo "OpenShell sandbox names are limited to 19 characters: $sandbox_name" >&2
  exit 2
fi
case "$policy_mode" in
  strict)
    ;;
  docker-desktop)
    echo "WARNING: Docker Desktop mode continues without required Landlock enforcement." >&2
    ;;
  *)
    echo "NEMO_EXPERIMENTALIST_POLICY_MODE must be strict or docker-desktop" >&2
    exit 2
    ;;
esac
if [[ ! -f "$policy_path" ]]; then
  echo "Run-specific OpenShell policy does not exist: $policy_path" >&2
  exit 2
fi

cleanup() {
  if [[ "${NEMO_EXPERIMENTALIST_KEEP_SANDBOX:-0}" != "1" ]]; then
    openshell sandbox delete "$sandbox_name" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

create_args=(
  sandbox create
  --name "$sandbox_name"
  --from "$image"
  --policy "$policy_path"
  --no-auto-providers
  --provider "$bridge_provider"
  --upload "$input_dir:/sandbox/input"
  --env "NMP_BASE_URL=$platform_url"
  --env "NEMO_EXPERIMENTALIST_OPEN_SHELL_RUNTIME=1"
  --env "NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_URL=$bridge_url"
  --env "NEMO_DEFAULT_MODEL=$NEMO_DEFAULT_MODEL"
  --env "NEMO_FAST_MODEL=$NEMO_FAST_MODEL"
)

openshell "${create_args[@]}" -- /bin/true

openshell sandbox exec --name "$sandbox_name" -- \
  /bin/bash -c '
    set -euo pipefail
    test "$NEMO_EXPERIMENTALIST_OPEN_SHELL_RUNTIME" = 1
    if command -v docker >/dev/null 2>&1; then
      echo "Experimentalist runtime unexpectedly contains Docker" >&2
      exit 1
    fi
    if [[ -e /var/run/docker.sock || -e /run/docker.sock ]]; then
      echo "Experimentalist runtime unexpectedly exposes a Docker socket" >&2
      exit 1
    fi
    if [[ -z "${NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_TOKEN:-}" ]]; then
      echo "OpenShell did not inject the Harbor bridge credential placeholder" >&2
      exit 1
    fi
  '

openshell sandbox exec --name "$sandbox_name" --workdir "$remote_input" -- \
  /app/.venv/bin/python -m nemo_experimentalist_plugin.openshell.inner \
    --manifest "$remote_input/run.json" \
    --output /sandbox/output

mkdir -p "$output_dir"
openshell sandbox download "$sandbox_name" /sandbox/output "$output_dir"
