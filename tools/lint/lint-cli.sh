#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail
# Verify CLI is up to date (make update-cli leaves no uncommitted changes).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${CI_PROJECT_DIR:-$(cd "${SCRIPT_DIR}/../.." && pwd)}"
cd "${PROJECT_ROOT}"

make update-cli
git add "${PROJECT_ROOT}/sdk/python/"
git diff --cached --exit-code "${PROJECT_ROOT}/sdk/python/" > "${PROJECT_ROOT}/diff.txt" || {
  echo "Run 'make update-cli' to update the CLI."
  exit 1
}
