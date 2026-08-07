#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
WEB_DIR="$REPO_ROOT/web"

# --- Toolchain availability ---

for tool in node pnpm; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "$tool is not on PATH."
    if [ -n "${NMP_SKIP_MISE:-}" ]; then
      echo "NMP_SKIP_MISE is set, so $tool has to come from your PATH."
      echo "Install it, or re-run without NMP_SKIP_MISE to use the mise-managed one."
    else
      echo "Run 'make verify-mise' to install the pinned toolchain."
    fi
    exit 1
  fi
done

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
