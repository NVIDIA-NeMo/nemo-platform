#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

if ! command -v openshell >/dev/null 2>&1; then
  echo "openshell CLI is required" >&2
  exit 127
fi
if [[ -z "${NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_TOKEN:-}" ]]; then
  echo "NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_TOKEN is required on the host" >&2
  exit 2
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
profile_source="$script_dir/provider-profiles/nemo-experimentalist-harbor-bridge.yaml"
profile_dir="${NEMO_EXPERIMENTALIST_PROVIDER_PROFILE_DIR:?provider profile directory is required}"
bridge_provider="${NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_PROVIDER:-nemo-experimentalist-harbor-bridge}"
bridge_provider_type="nemo-experimentalist-harbor-bridge"
inference_provider="${NEMO_EXPERIMENTALIST_INFERENCE_PROVIDER:-nemo-experimentalist-inference}"
inference_provider_type="${NEMO_EXPERIMENTALIST_INFERENCE_PROVIDER_TYPE:-nvidia}"
inference_model="${NEMO_EXPERIMENTALIST_INFERENCE_MODEL:-}"
if [[ -z "$inference_model" && -n "${EXPERIMENTALIST_SMART_MODEL_NAME:-}" ]]; then
  inference_model="${EXPERIMENTALIST_SMART_MODEL_NAME#openai/}"
fi

mkdir -p "$profile_dir"
cp "$profile_source" "$profile_dir/"

openshell settings set --global --key providers_v2_enabled --value true --yes

bridge_provider_created=0
cleanup_failed_setup() {
  status=$?
  if [[ "$status" -ne 0 && "$bridge_provider_created" == "1" ]]; then
    openshell provider delete "$bridge_provider" >/dev/null 2>&1 || \
      echo "WARNING: could not delete partially configured provider $bridge_provider" >&2
  fi
  exit "$status"
}
trap cleanup_failed_setup EXIT

if openshell provider get "$bridge_provider" >/dev/null 2>&1; then
  openshell provider delete "$bridge_provider"
fi
if openshell provider profile export "$bridge_provider_type" -o yaml >/dev/null 2>&1; then
  openshell provider profile delete "$bridge_provider_type"
fi
openshell provider profile lint --from "$profile_dir"
openshell provider profile import --from "$profile_dir"

bridge_provider_created=1
openshell provider create \
  --name "$bridge_provider" \
  --type "$bridge_provider_type" \
  --credential NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_TOKEN

if [[ -n "$inference_model" ]]; then
  inference_set_args=(inference set --provider "$inference_provider" --model "$inference_model")
  if openshell provider get "$inference_provider" >/dev/null 2>&1; then
    openshell provider delete "$inference_provider"
  fi
  if [[ "$inference_provider_type" == "nvidia" ]]; then
    openshell provider create \
      --name "$inference_provider" \
      --type "$inference_provider_type" \
      --credential NVIDIA_API_KEY \
      --config NVIDIA_BASE_URL=https://inference-api.nvidia.com/v1
    # OpenShell 0.0.92's generic probe is rejected by the Inference Hub GPT-5
    # proxy even though normal routed requests are supported. This skips only
    # that setup probe; OpenShell still pins and enforces the runtime route.
    inference_set_args+=(--no-verify)
  else
    openshell provider create \
      --name "$inference_provider" \
      --type "$inference_provider_type" \
      --from-existing
  fi
  openshell "${inference_set_args[@]}"
fi

trap - EXIT
