#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

usage() {
  echo "usage: $0 WORKSPACE_DIR [experimentalist run options...]" >&2
}

if [[ $# -lt 1 ]]; then
  usage
  exit 2
fi

workspace_dir="$(cd "$1" && pwd)"
shift
smoke_output="${NEMO_EXPERIMENTALIST_SMOKE_OUTPUT:-$workspace_dir/tmp/experimentalist-full-run-smoke-$$}"
nemo_bin="${NEMO_EXPERIMENTALIST_CLI:-$(command -v nemo || true)}"

if [[ -e "$smoke_output" ]]; then
  echo "smoke output already exists: $smoke_output" >&2
  exit 2
fi

if [[ -z "$nemo_bin" || ! -x "$nemo_bin" ]]; then
  echo "nemo CLI is required; set NEMO_EXPERIMENTALIST_CLI to its executable path" >&2
  exit 127
fi

(
  cd "$workspace_dir"
  "$nemo_bin" experimentalist run --experiment-dir "$smoke_output" "$@"
)

analysis_file="$(find "$smoke_output" -type f -path "*/eval-and-optimize/analysis/round-*.md" -print -quit)"
if [[ -z "$analysis_file" ]]; then
  echo "full-run smoke produced no round analysis under $smoke_output" >&2
  exit 1
fi

if grep -R -n -F "analysis_error" "$smoke_output"; then
  echo "full-run smoke degraded trace analysis to analysis_error" >&2
  exit 1
fi

echo "OpenShell full-run smoke passed: $smoke_output"
