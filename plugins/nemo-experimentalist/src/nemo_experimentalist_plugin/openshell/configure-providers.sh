#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

if ! command -v openshell >/dev/null 2>&1; then
  echo "openshell CLI is required: https://docs.nvidia.com/openshell/latest/get-started/quickstart" >&2
  exit 127
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
profile_template_dir="$script_dir/provider-profiles"
profile_dir="${NEMO_EXPERIMENTALIST_PROVIDER_PROFILE_DIR:-$PWD/tmp/experimentalist-openshell-provider-profiles}"
bridge_provider="${NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_PROVIDER:-nemo-experimentalist-harbor-bridge}"
inference_provider="${NEMO_EXPERIMENTALIST_INFERENCE_PROVIDER:-nemo-experimentalist-inference}"
inference_provider_type="${NEMO_EXPERIMENTALIST_INFERENCE_PROVIDER_TYPE:-nvidia}"
inference_model="${NEMO_EXPERIMENTALIST_INFERENCE_MODEL:-}"
if [[ -z "$inference_model" && -n "${EXPERIMENTALIST_SMART_MODEL_NAME:-}" ]]; then
  # NOOA prefixes OpenAI-compatible transports with "openai/"; OpenShell needs
  # the provider's raw model ID when configuring inference.local.
  inference_model="${EXPERIMENTALIST_SMART_MODEL_NAME#openai/}"
fi
gitlab_host="${NEMO_EXPERIMENTALIST_GITLAB_HOST:-${GITLAB_HOST:-gitlab.com}}"

if [[ "$inference_provider_type" == "nvidia" && -z "${NVIDIA_API_KEY:-}" && -n "${NVIDIA_INTERNAL_API_KEY:-}" ]]; then
  export NVIDIA_API_KEY="$NVIDIA_INTERNAL_API_KEY"
fi

if [[ -z "${NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_TOKEN:-}" ]]; then
  echo "NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_TOKEN is required" >&2
  exit 2
fi

if [[ ! "$gitlab_host" =~ ^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$ ]]; then
  echo "invalid GitLab hostname: $gitlab_host" >&2
  exit 2
fi

mkdir -p "$profile_dir"
for profile_path in "$profile_template_dir"/*.yaml; do
  sed "s/host: gitlab\\.com/host: $gitlab_host/g" "$profile_path" >"$profile_dir/$(basename "$profile_path")"
done

delete_provider_if_present() {
  local provider_name="$1"

  # These names are dedicated to this runtime. Recreating them makes profile
  # changes deterministic and migrates the earlier generic bridge provider.
  if openshell provider get "$provider_name" >/dev/null 2>&1; then
    openshell provider delete "$provider_name"
  fi
}

delete_profile_if_present() {
  local profile_name="$1"
  local profile_yaml
  local profile_scope

  if ! profile_yaml="$(openshell provider profile export "$profile_name" 2>/dev/null)"; then
    return
  fi

  profile_scope="$(awk '$1 == "scope:" { print $2; exit }' <<<"$profile_yaml")"
  if [[ "$profile_scope" == "platform" ]]; then
    openshell provider profile delete --global "$profile_name"
  else
    openshell provider profile delete "$profile_name"
  fi
}

replace_provider_from_existing() {
  local provider_name="$1"
  local provider_type="$2"
  shift 2

  delete_provider_if_present "$provider_name"
  openshell provider create --name "$provider_name" --type "$provider_type" --from-existing "$@"
}

replace_provider_with_credential() {
  local provider_name="$1"
  local provider_type="$2"
  local credential_env="$3"

  delete_provider_if_present "$provider_name"

  # Custom profiles are not part of the legacy gateway's built-in credential
  # discovery. The key-only form reads the value from the environment, keeping
  # it out of command arguments.
  openshell provider create \
    --name "$provider_name" \
    --type "$provider_type" \
    --credential "$credential_env"
}

for provider_name in \
  "$bridge_provider" \
  nemo-experimentalist-github-read \
  nemo-experimentalist-github-publish \
  nemo-experimentalist-gitlab-read \
  nemo-experimentalist-gitlab-publish; do
  delete_provider_if_present "$provider_name"
done

for profile_path in "$profile_dir"/*.yaml; do
  profile_id="$(basename "$profile_path" .yaml)"
  delete_profile_if_present "$profile_id"
done

# Provider credentials are injected without this gate, but provider endpoint
# policies are composed into sandbox policy only when providers v2 is enabled.
openshell settings set \
  --global \
  --key providers_v2_enabled \
  --value true \
  --yes

openshell provider profile lint --from "$profile_dir"
openshell provider profile import --from "$profile_dir"

replace_provider_with_credential \
  "$bridge_provider" \
  nemo-experimentalist-harbor-bridge \
  NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_TOKEN

if [[ -n "$inference_model" ]]; then
  if [[ "$inference_provider_type" == "nvidia" ]]; then
    replace_provider_from_existing \
      "$inference_provider" \
      "$inference_provider_type" \
      --config NVIDIA_BASE_URL=https://inference-api.nvidia.com/v1
  else
    replace_provider_from_existing "$inference_provider" "$inference_provider_type"
  fi
  openshell inference set --provider "$inference_provider" --model "$inference_model"
  echo "Configured inference.local with provider '$inference_provider' and model '$inference_model'."
else
  echo "Inference route unchanged. Set NEMO_EXPERIMENTALIST_INFERENCE_MODEL to configure inference.local."
fi

if [[ -n "${GH_TOKEN:-${GITHUB_TOKEN:-}}" ]]; then
  if [[ -n "${GH_TOKEN:-}" ]]; then
    github_credential_env=GH_TOKEN
  else
    github_credential_env=GITHUB_TOKEN
  fi
  replace_provider_with_credential \
    nemo-experimentalist-github-read \
    nemo-experimentalist-github-read \
    "$github_credential_env"
  replace_provider_with_credential \
    nemo-experimentalist-github-publish \
    nemo-experimentalist-github-publish \
    "$github_credential_env"
  echo "Configured GitHub read and publish providers."
else
  echo "GitHub providers skipped. Export GH_TOKEN or GITHUB_TOKEN to configure them."
fi

if [[ -n "${GITLAB_TOKEN:-}" ]]; then
  replace_provider_with_credential \
    nemo-experimentalist-gitlab-read \
    nemo-experimentalist-gitlab-read \
    GITLAB_TOKEN
  replace_provider_with_credential \
    nemo-experimentalist-gitlab-publish \
    nemo-experimentalist-gitlab-publish \
    GITLAB_TOKEN
  echo "Configured GitLab read and publish providers."
else
  echo "GitLab providers skipped. Export GITLAB_TOKEN to configure them."
fi
