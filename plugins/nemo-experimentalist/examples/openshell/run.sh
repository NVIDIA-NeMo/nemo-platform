#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

usage() {
  echo "usage: $0 WORKSPACE_DIR {doctor|run} [experimentalist options...]" >&2
}

if [[ $# -lt 2 ]]; then
  usage
  exit 2
fi

workspace_dir="$(cd "$1" && pwd)"
remote_workspace="/sandbox/project/$(basename "$workspace_dir")"
subcommand="$2"
shift 2

if [[ "$subcommand" != "doctor" && "$subcommand" != "run" ]]; then
  usage
  exit 2
fi

if ! command -v openshell >/dev/null 2>&1; then
  echo "openshell CLI is required: https://docs.nvidia.com/openshell/latest/get-started/quickstart" >&2
  exit 127
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
image="${NEMO_EXPERIMENTALIST_IMAGE:-nmp-experimentalist:local}"
sandbox_name="${NEMO_EXPERIMENTALIST_SANDBOX_NAME:-nemo-exp-$$}"
platform_url="${NMP_BASE_URL:-http://host.docker.internal:8080}"
bridge_url="${NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_URL:-http://host.docker.internal:8765}"
bridge_provider="${NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_PROVIDER:-nemo-experimentalist-harbor-bridge}"
output_dir="${NEMO_EXPERIMENTALIST_OUTPUT_DIR:-$workspace_dir/tmp/experimentalist-openshell}"
policy_mode="${NEMO_EXPERIMENTALIST_POLICY_MODE:-strict}"

if (( ${#sandbox_name} > 19 )); then
  echo "OpenShell sandbox names are limited to 19 characters: $sandbox_name" >&2
  exit 2
fi

case "$policy_mode" in
  strict)
    policy_path="$script_dir/policy.yaml"
    ;;
  docker-desktop)
    policy_path="$script_dir/policy.docker-desktop.yaml"
    echo "WARNING: Docker Desktop mode continues without Landlock filesystem enforcement." >&2
    ;;
  *)
    echo "NEMO_EXPERIMENTALIST_POLICY_MODE must be 'strict' or 'docker-desktop'" >&2
    exit 2
    ;;
esac

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
  --upload "$workspace_dir:/sandbox/project"
  --env "NMP_BASE_URL=$platform_url"
  --env "NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_URL=$bridge_url"
  --env "EXPERIMENTALIST_API_BASE=https://inference.local/v1"
  --env "EXPERIMENTALIST_API_KEY=not-used"
)

for name in \
  EXPERIMENTALIST_SMART_MODEL_NAME \
  EXPERIMENTALIST_MID_MODEL_NAME \
  EXPERIMENTALIST_FAST_MODEL_NAME; do
  if [[ -n "${!name:-}" ]]; then
    create_args+=(--env "$name=${!name}")
  fi
done

# Provision non-interactively without attaching a host credential provider.
# OpenShell keeps the sandbox alive after the initial command exits; subsequent
# work runs through `sandbox exec`.
openshell "${create_args[@]}" -- /bin/true

if [[ "$subcommand" == "doctor" ]]; then
  openshell sandbox exec --name "$sandbox_name" --workdir "$remote_workspace" -- \
    /app/.venv/bin/nemo experimentalist doctor "$@"
  exit
fi

openshell sandbox exec --name "$sandbox_name" --workdir "$remote_workspace" -- \
  /app/.venv/bin/nemo experimentalist run --experiment-dir /sandbox/output "$@"

mkdir -p "$output_dir"
openshell sandbox download "$sandbox_name" /sandbox/output "$output_dir"
