#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

set -uo pipefail

mkdir -p /logs/verifier
OUTPUT=/app/artifacts/output.txt
reward=0.0
format_ok=0.0
if [ -f "$OUTPUT" ]; then
  format_ok=1.0
  if cmp -s /tests/expected.txt "$OUTPUT"; then
    reward=1.0
  fi
fi
printf '{"reward": %s, "format_ok": %s}\n' "$reward" "$format_ok" > /logs/verifier/reward.json
cat /logs/verifier/reward.json
