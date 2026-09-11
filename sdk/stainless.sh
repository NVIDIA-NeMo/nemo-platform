#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

echo "Stainless Python SDK generation is disabled." >&2
echo "No automated lint can prove legacy Stainless SDK compatibility; use source-owned typed clients or manually review compatibility." >&2
exit 1
