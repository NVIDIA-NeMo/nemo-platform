#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

prompt="${1:-}"
lower_prompt="${prompt,,}"
gitlab_host="${GITLAB_HOST:-gitlab.com}"
lower_gitlab_host="${gitlab_host,,}"

if [[ "$lower_prompt" == *username*github.com* ]]; then
  printf '%s\n' "x-access-token"
elif [[ "$lower_prompt" == *password*github.com* ]]; then
  if [[ -z "${GH_TOKEN:-${GITHUB_TOKEN:-}}" ]]; then
    echo "GitHub provider placeholder is unavailable" >&2
    exit 1
  fi
  printf '%s\n' "${GH_TOKEN:-${GITHUB_TOKEN}}"
elif [[ "$lower_prompt" == *username*"$lower_gitlab_host"* ]]; then
  printf '%s\n' "oauth2"
elif [[ "$lower_prompt" == *password*"$lower_gitlab_host"* ]]; then
  if [[ -z "${GITLAB_TOKEN:-}" ]]; then
    echo "GitLab provider placeholder is unavailable" >&2
    exit 1
  fi
  printf '%s\n' "$GITLAB_TOKEN"
else
  echo "unsupported Git credential prompt: $prompt" >&2
  exit 1
fi
