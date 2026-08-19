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

trap - EXIT
