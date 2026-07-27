#!/usr/bin/env bash
# Run both OpenSandbox runtime verifications (crun then kata-qemu).
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"${DIR}/crun.sh"
"${DIR}/kata-qemu.sh"
echo "==> PASS all OpenSandbox runtime verifications"
