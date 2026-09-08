#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# The agent phase is expected to fail before this verifier runs. Keep a valid
# fallback verifier so an unexpected invocation still writes well-formed rewards.

set -uo pipefail

mkdir -p /logs/verifier
printf '{"reward": 0.0, "format_ok": 0.0}\n' > /logs/verifier/reward.json
cat /logs/verifier/reward.json
