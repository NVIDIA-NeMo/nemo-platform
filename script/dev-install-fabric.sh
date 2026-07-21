#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Dev-only: set up the local dependencies the Fabric eval runner needs so the type checker and a
# live FabricAgentRuntime run work end-to-end:
#   1. the native `nemo-fabric` SDK (with the codex + relay + runtime extras) into the project venv, and
#   2. the `nemo-relay` gateway binary (required for ATIF trajectory capture on out-of-process
#      harnesses like codex).
# This is an imperative install — it does NOT touch uv.lock, and CI intentionally runs without it
# (the `# ty: ignore[unresolved-import]` in agent_eval/runtimes/fabric/runtime.py covers the CI case).
#
# On Linux you no longer need this script for the SDK: `nemo-fabric` now publishes wheels to PyPI and
# is a locked, Linux-gated `fabric` extra on nemo-evaluator-sdk — install it with
# `uv sync --extra fabric` (or `uv pip install "nemo-evaluator-sdk[fabric]"`). This script remains
# the path for macOS-native dev, where nemo-fabric-runtime has no wheel yet (manylinux only).
#
# The `nemo-relay` gateway is NOT on PyPI (the pip `nemo-relay` package ships only the Python
# bindings, not the daemon), but NeMo-Relay publishes prebuilt gateway binaries on its GitHub
# releases (macOS arm64 + static-musl Linux). We download one directly — no NeMo-Relay checkout or
# Rust build needed. A live codex run also needs the `codex` CLI + `codex login` auth.
# See plugins/nemo-evaluator/docs/design/fabric-runner-integration.md.
#
# Usage:
#   script/dev-install-fabric.sh                                  # SDK from checkout + downloaded gateway
#   NEMO_FABRIC_REPO=/path/to/NeMo-Fabric script/dev-install-fabric.sh
#   NEMO_RELAY_VERSION=0.6.0-rc.2 script/dev-install-fabric.sh    # pin a different gateway release
#   NEMO_RELAY_REPO=/path/to/NeMo-Relay script/dev-install-fabric.sh  # force a source build instead
#   script/dev-install-fabric.sh --uninstall                     # restore the CI-equivalent state
set -euo pipefail

VENV_PY=".venv/bin/python"
if [ ! -x "$VENV_PY" ]; then
  echo "Project venv not found at $VENV_PY. Run 'make bootstrap-python' (see SETUP.md) first." >&2
  exit 1
fi

if [ "${1:-}" = "--uninstall" ]; then
  # Remove the runtime (which provides the importable `nemo_fabric`) + adapters, not just the
  # metapackage, so `import nemo_fabric` fails again and the venv matches the CI/lock state.
  uv pip uninstall --python "$VENV_PY" \
    nemo-fabric nemo-fabric-runtime nemo-fabric-adapters-codex nemo-fabric-adapters-common
  echo "Removed nemo-fabric; venv is back to the lock-consistent / CI-equivalent state."
  echo "(The nemo-relay gateway binary, if installed, is left in place — remove ~/.cargo/bin/nemo-relay manually if desired.)"
  exit 0
fi

# On macOS the `runtime` extra builds nemo-fabric-runtime (a Rust/pyo3 extension) from source via
# maturin — there is no macOS wheel — so cargo must be on PATH for the SDK install. The relay gateway
# is downloaded prebuilt below and does NOT need cargo unless a source build is forced via
# NEMO_RELAY_REPO.
if ! command -v cargo >/dev/null 2>&1 && [ -f "$HOME/.cargo/env" ]; then
  # shellcheck disable=SC1091
  . "$HOME/.cargo/env"
fi
if ! command -v cargo >/dev/null 2>&1; then
  echo "cargo (Rust toolchain) not found; install it to build the native components: https://rustup.rs" >&2
  exit 1
fi

# 1. nemo-fabric SDK into the project venv. The `runtime` extra provides the importable `nemo_fabric`
#    module (built from source on macOS); `codex`+`relay` add the codex adapter + ATIF trajectory deps.
FABRIC_REPO="${NEMO_FABRIC_REPO:-$HOME/workspace/NeMo-Fabric}"
if [ ! -d "$FABRIC_REPO" ]; then
  echo "NeMo-Fabric checkout not found at: $FABRIC_REPO" >&2
  echo "Clone it (gh repo clone NVIDIA/NeMo-Fabric) or set NEMO_FABRIC_REPO=/path/to/NeMo-Fabric." >&2
  exit 1
fi
echo "Building + installing nemo-fabric[codex,relay,runtime] from $FABRIC_REPO into $VENV_PY ..."
uv pip install --python "$VENV_PY" "${FABRIC_REPO}[codex,relay,runtime]"
"$VENV_PY" -c "import nemo_fabric; from nemo_fabric import Fabric, RunResult; print('nemo_fabric OK:', nemo_fabric.__file__)"

# 2. nemo-relay gateway binary — required for live ATIF trajectory capture on out-of-process
#    harnesses (codex). The pip `nemo-relay` package does NOT ship this daemon, so we download the
#    prebuilt binary from the NeMo-Relay GitHub releases (override with NEMO_RELAY_VERSION). Set
#    NEMO_RELAY_REPO to force a source build (e.g. on a platform with no prebuilt asset).
NEMO_RELAY_VERSION="${NEMO_RELAY_VERSION:-0.5.0}"
RELAY_BIN_DIR="${CARGO_HOME:-$HOME/.cargo}/bin"
# Skip provisioning only when an existing nemo-relay already matches NEMO_RELAY_VERSION, so an
# explicit version request is honored rather than silently short-circuited by any PATH match.
need_relay_install=1
if command -v nemo-relay >/dev/null 2>&1; then
  installed_relay_ver="$(nemo-relay --version 2>/dev/null | awk '{print $NF}')"
  if [ "$installed_relay_ver" = "$NEMO_RELAY_VERSION" ]; then
    echo "nemo-relay gateway already on PATH at requested version ${installed_relay_ver}: $(command -v nemo-relay)"
    need_relay_install=0
  else
    echo "nemo-relay ${installed_relay_ver:-?} on PATH differs from requested ${NEMO_RELAY_VERSION}; (re)installing ..."
  fi
fi

if [ "$need_relay_install" = 1 ]; then
  # Map host platform -> NeMo-Relay release target triple (no Intel-macOS asset is published).
  relay_target=""
  case "$(uname -s):$(uname -m)" in
    Darwin:arm64) relay_target="aarch64-apple-darwin" ;;
    Linux:x86_64) relay_target="x86_64-unknown-linux-musl" ;;
    Linux:aarch64 | Linux:arm64) relay_target="aarch64-unknown-linux-musl" ;;
  esac

  if [ -n "$relay_target" ] && [ -z "${NEMO_RELAY_REPO:-}" ]; then
    asset="nemo-relay-cli-${relay_target}-${NEMO_RELAY_VERSION}"
    base="https://github.com/NVIDIA/NeMo-Relay/releases/download/${NEMO_RELAY_VERSION}"
    tmp="$(mktemp -d)"
    echo "Downloading nemo-relay gateway ${NEMO_RELAY_VERSION} (${relay_target}) from GitHub releases ..."
    curl -fsSL -o "${tmp}/nemo-relay" "${base}/${asset}"
    curl -fsSL -o "${tmp}/nemo-relay.sha256" "${base}/${asset}.sha256"
    want="$(awk '{print $1}' "${tmp}/nemo-relay.sha256")"
    if command -v sha256sum >/dev/null 2>&1; then
      got="$(sha256sum "${tmp}/nemo-relay" | awk '{print $1}')"
    else
      got="$(shasum -a 256 "${tmp}/nemo-relay" | awk '{print $1}')"
    fi
    if [ "$want" != "$got" ]; then
      echo "Checksum mismatch for ${asset}: expected ${want}, got ${got}" >&2
      rm -rf "$tmp"
      exit 1
    fi
    mkdir -p "$RELAY_BIN_DIR"
    install -m 0755 "${tmp}/nemo-relay" "${RELAY_BIN_DIR}/nemo-relay"
    rm -rf "$tmp"
    echo "nemo-relay gateway installed: ${RELAY_BIN_DIR}/nemo-relay ($("${RELAY_BIN_DIR}/nemo-relay" --version 2>/dev/null || echo '?'))"
    # Warn if the install dir isn't on PATH — live tests resolve the gateway via shutil.which().
    case ":${PATH}:" in
      *":${RELAY_BIN_DIR}:"*) : ;;
      *) echo "NOTE: ${RELAY_BIN_DIR} is not on PATH — add it so 'nemo-relay' is found: export PATH=\"${RELAY_BIN_DIR}:\$PATH\"" >&2 ;;
    esac
  else
    # Fallback: source build from a NeMo-Relay checkout (no prebuilt asset for this platform, e.g.
    # Intel macOS, or NEMO_RELAY_REPO set explicitly to force a build).
    RELAY_REPO="${NEMO_RELAY_REPO:-$HOME/workspace/NeMo-Relay}"
    if [ ! -d "$RELAY_REPO" ]; then
      echo "No prebuilt nemo-relay gateway for $(uname -s):$(uname -m) and no NeMo-Relay checkout at: $RELAY_REPO" >&2
      echo "Clone NVIDIA/NeMo-Relay (or set NEMO_RELAY_REPO), or set NEMO_RELAY_VERSION to a release with an asset for your platform." >&2
      exit 1
    fi
    echo "Building + installing the nemo-relay gateway from $RELAY_REPO (cargo install) ..."
    cargo install --path "$RELAY_REPO/crates/cli" --locked
    echo "nemo-relay gateway installed: $(command -v nemo-relay) ($(nemo-relay --version 2>/dev/null || echo '?'))"
  fi
fi

cat <<'EOF'

Done. Fabric's real types now resolve (ty enforces them; you'll see 2 harmless "unused ty: ignore"
warnings while nemo-fabric is installed), and live FabricAgentRuntime runs can capture ATIF
trajectories (needs the `codex` CLI + `codex login` for a codex-harness run).

Restore the CI-equivalent state with:
  script/dev-install-fabric.sh --uninstall
EOF
