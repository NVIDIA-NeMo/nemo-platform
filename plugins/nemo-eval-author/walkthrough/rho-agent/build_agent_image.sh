#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REVISION="${RHO_REVISION:-04b9cfa1c940e8c3fd6ecdd6888f9fabd0110558}"
TAG="${RHO_AGENT_IMAGE_TAG:-${REVISION:0:12}}"
IMAGE="${RHO_AGENT_IMAGE:-nemo-eval-author/rho-agent-harbor:${TAG}}"

exec docker build \
  --file "${SCRIPT_DIR}/Dockerfile.agent" \
  --build-arg "RHO_REVISION=${REVISION}" \
  --tag "${IMAGE}" \
  "${SCRIPT_DIR}"
