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
policy_path="$script_dir/policy.yaml"
image="${NEMO_EXPERIMENTALIST_IMAGE:-nmp-experimentalist:local}"
sandbox_name="${NEMO_EXPERIMENTALIST_SANDBOX_NAME:-experimentalist-${USER:-user}-$$}"
platform_url="${NMP_BASE_URL:-http://host.docker.internal:8080}"
output_dir="${NEMO_EXPERIMENTALIST_OUTPUT_DIR:-$workspace_dir/tmp/experimentalist-openshell}"

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
  --upload "$workspace_dir:/sandbox/project"
  --env "NMP_BASE_URL=$platform_url"
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
  openshell sandbox exec --name "$sandbox_name" --workdir /sandbox/project -- \
    nemo experimentalist doctor "$@"
  exit
fi

# The current local Harbor evaluator will fail its Docker preflight in this
# sandbox by design. Once the platform-evaluator adapter lands, this same
# invocation becomes the full sandboxed control-plane path.
openshell sandbox exec --name "$sandbox_name" --workdir /sandbox/project -- \
  nemo experimentalist run --experiment-dir /sandbox/output "$@"

mkdir -p "$output_dir"
openshell sandbox download "$sandbox_name" /sandbox/output "$output_dir"
