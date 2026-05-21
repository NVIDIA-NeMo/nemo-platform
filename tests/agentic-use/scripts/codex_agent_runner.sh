#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail
model_args=()
if [ -n "${AGENT_MODEL:-}" ]; then
  model_args=(--model "${AGENT_MODEL}")
fi
config_args=(@@CODEX_CONFIG_ARGS@@)
export CODEX_HOME="/home/harbor/codex-benchmark-home"
rm -rf "$CODEX_HOME"
mkdir -p "$CODEX_HOME"
if [ -f /tmp/codex_host_auth.json ]; then
  cp /tmp/codex_host_auth.json "$CODEX_HOME/auth.json"
fi
# Run from /app like the other direct agent backends. Only auth is optionally
# copied into a fresh container-local CODEX_HOME; host config is not reproduced.
set +e
codex exec \
  --ignore-user-config \
  --skip-git-repo-check \
  --sandbox danger-full-access \
  --cd /app \
  --output-last-message /logs/agent/final_message.txt \
  --json \
  "${model_args[@]}" \
  "${config_args[@]}" \
  - < @@INSTRUCTION_CONTAINER@@ \
  > /tmp/nat_agent.log 2> /tmp/nat_agent.stderr
rc=$?
set -e
cp /tmp/nat_agent.log /logs/agent/nat_agent.log 2>/dev/null || true
cp /tmp/nat_agent.stderr /logs/agent/nat_agent.stderr 2>/dev/null || true
exit $rc
