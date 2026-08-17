#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail
# Verify config reference doc is up to date.
uv run --frozen generate-config-docs
git diff --exit-code docs/set-up/config-reference.mdx || {
  echo "Config reference doc is out of date. Run 'uv run generate-config-docs' and commit docs/set-up/config-reference.mdx"
  exit 1
}
