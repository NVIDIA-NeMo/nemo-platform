#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
WEB_DIR="$REPO_ROOT/web"

# --- Toolchain availability ---

if ! command -v node >/dev/null 2>&1; then
  echo "node is not on PATH." >&2
  exit 1
fi

if [[ -n "${PNPM_VERSION:-}" ]]; then
  if ! command -v corepack >/dev/null 2>&1; then
    echo "corepack is not on PATH." >&2
    exit 1
  fi
  pnpm() {
    corepack "pnpm@${PNPM_VERSION}" "$@"
  }
elif ! command -v pnpm >/dev/null 2>&1; then
  echo "pnpm is not on PATH." >&2
  echo "Install it, or rerun without TOOLCHAIN=system to use Flox." >&2
  exit 1
fi

# --- Engine compatibility check ---

node_current="$(node --version)"
pnpm_current="$(pnpm --version)"
node_required="$(cd "$WEB_DIR" && node -p "require('./package.json').engines.node")"
pnpm_required="$(cd "$WEB_DIR" && node -p "require('./package.json').engines.pnpm")"

install_output="$(cd "$WEB_DIR" && CI=true pnpm install --frozen-lockfile --lockfile-only --config.engine-strict=true 2>&1)" \
  && install_status=0 || install_status=$?

if [ -n "$install_output" ]; then
  printf "%s\n" "$install_output"
fi

if [ "$install_status" -ne 0 ]; then
  echo ""
  case "$install_output" in
    *ERR_PNPM_UNSUPPORTED_ENGINE*)
      echo "Studio assets were not built because Node.js/pnpm do not satisfy web/package.json engines."
      ;;
    *)
      echo "Studio assets were not built because web dependency bootstrap failed before the asset build."
      echo "Check the pnpm output above for details and retry the install."
      ;;
  esac
  echo "Current: node $node_current, pnpm $pnpm_current"
  echo "Required: node $node_required, pnpm $pnpm_required"
  echo ""
  echo "API services can still run, but Studio UI will be unavailable until assets are built."
  echo "After upgrading Node/pnpm, run:"
  echo "  make bootstrap-studio"
  exit 1
fi
