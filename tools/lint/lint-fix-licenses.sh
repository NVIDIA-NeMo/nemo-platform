#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail
# Run license generation. If licenses.jsonl did not change, restore third_party to
# discard osv-scanner noise (requirements*.txt, osv-licenses*.json).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${CI_PROJECT_DIR:-$(cd "${SCRIPT_DIR}/../.." && pwd)}"
cd "${PROJECT_ROOT}" || exit 1

make update-licenses

if git diff --quiet third_party/licenses.jsonl; then
  echo "No meaningful changes to license files — restoring third_party to discard osv-scanner noise"
  git restore third_party
fi
