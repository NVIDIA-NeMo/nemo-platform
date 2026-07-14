#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Dev-only: set up the local dependencies the Fabric eval runner needs so the type checker and a
# live FabricAgentRuntime run work end-to-end:
#   1. the native `nemo-fabric` SDK (with the codex + relay extras) into the project venv, and
#   2. the `nemo-relay` gateway binary (required for ATIF trajectory capture on the codex harness).
# This is an imperative install — it does NOT touch uv.lock, and CI intentionally runs without it
# (the `# ty: ignore[unresolved-import]` in agent_eval/runtimes/fabric/runtime.py covers the CI case).
#
# nemo-fabric and the nemo-relay gateway are private/native builds with no published wheel/binary in
# our index, so they can't be locked dependencies yet (see
# plugins/nemo-evaluator/docs/design/fabric-runner-integration.md, Tier 3). A live codex run also
# needs the `codex` CLI + `codex login` auth.
#
# Usage:
#   script/dev-install-fabric.sh                 # NeMo-Fabric+NeMo-Relay under $HOME/workspace
#   NEMO_FABRIC_REPO=... NEMO_RELAY_REPO=... script/dev-install-fabric.sh
#   script/dev-install-fabric.sh --uninstall     # restore the CI-equivalent (no nemo-fabric) state
set -euo pipefail

VENV_PY=".venv/bin/python"
if [ ! -x "$VENV_PY" ]; then
  echo "Project venv not found at $VENV_PY. Run 'make bootstrap-python' (see SETUP.md) first." >&2
  exit 1
fi

if [ "${1:-}" = "--uninstall" ]; then
  uv pip uninstall --python "$VENV_PY" nemo-fabric
  echo "Removed nemo-fabric; venv is back to the lock-consistent / CI-equivalent state."
  echo "(The nemo-relay gateway binary, if installed, is left in place — remove it from ~/.cargo/bin manually if desired.)"
  exit 0
fi

# nemo-fabric builds a Rust/pyo3 extension via maturin and the relay gateway is a Rust CLI, so cargo
# must be on PATH.
if ! command -v cargo >/dev/null 2>&1 && [ -f "$HOME/.cargo/env" ]; then
  # shellcheck disable=SC1091
  . "$HOME/.cargo/env"
fi
if ! command -v cargo >/dev/null 2>&1; then
  echo "cargo (Rust toolchain) not found; install it to build the native components: https://rustup.rs" >&2
  exit 1
fi

# 1. nemo-fabric SDK (+ codex and relay extras) into the project venv.
FABRIC_REPO="${NEMO_FABRIC_REPO:-$HOME/workspace/NeMo-Fabric}"
if [ ! -d "$FABRIC_REPO" ]; then
  echo "NeMo-Fabric checkout not found at: $FABRIC_REPO" >&2
  echo "Clone it (gh repo clone NVIDIA/NeMo-Fabric) or set NEMO_FABRIC_REPO=/path/to/NeMo-Fabric." >&2
  exit 1
fi
echo "Building + installing nemo-fabric[codex,relay] from $FABRIC_REPO into $VENV_PY ..."
uv pip install --python "$VENV_PY" "${FABRIC_REPO}[codex,relay]"
"$VENV_PY" -c "import nemo_fabric; from nemo_fabric import Fabric, RunResult; print('nemo_fabric OK:', nemo_fabric.__file__)"

# 2. nemo-relay gateway binary (codex -> OTLP -> gateway -> trajectory-*.atif.json). Required for
#    trajectory capture; the pip `nemo-relay` package does NOT ship this executable.
if command -v nemo-relay >/dev/null 2>&1; then
  echo "nemo-relay gateway already on PATH: $(command -v nemo-relay) ($(nemo-relay --version 2>/dev/null || echo '?'))"
else
  RELAY_REPO="${NEMO_RELAY_REPO:-$HOME/workspace/NeMo-Relay}"
  if [ ! -d "$RELAY_REPO" ]; then
    echo "nemo-relay gateway not on PATH and NeMo-Relay checkout not found at: $RELAY_REPO" >&2
    echo "Clone it (gh repo clone NVIDIA/NeMo-Relay) or set NEMO_RELAY_REPO=/path/to/NeMo-Relay." >&2
    echo "Trajectory (ATIF) capture will fail without the nemo-relay gateway." >&2
    exit 1
  fi
  echo "Building + installing the nemo-relay gateway from $RELAY_REPO (cargo install) ..."
  cargo install --path "$RELAY_REPO/crates/cli" --locked
  echo "nemo-relay gateway installed: $(command -v nemo-relay) ($(nemo-relay --version 2>/dev/null || echo '?'))"
fi

cat <<'EOF'

Done. Fabric's real types now resolve (ty enforces them; you'll see 2 harmless "unused ty: ignore"
warnings while nemo-fabric is installed), and live FabricAgentRuntime runs can capture ATIF
trajectories (needs the `codex` CLI + `codex login` for a codex-harness run).

Restore the CI-equivalent state with:
  script/dev-install-fabric.sh --uninstall
EOF
