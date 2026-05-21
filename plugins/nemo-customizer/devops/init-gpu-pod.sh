#!/usr/bin/env bash
# Bootstrap a fresh `test-unsloth-anubhutiv` GPU pod:
#   1. OS deps + Python 3.11 + uv
#   2. Place Platform repo under /workspace/Platform (kubectl cp from your mac)
#   3. Install nemo-customizer-plugin into a host venv (so `nemo` is on PATH)
#   4. Create /workspace/.venv-unsloth if missing and install the [unsloth] extra
#   5. Run the smoke test via `--venv /workspace/.venv-unsloth`
#
# Usage (from your mac):
#   kubectl apply -f plugins/nemo-customizer/devops/gpu-pod.yaml
#   kubectl cp /Users/anubhutiv/workspace/Platform \
#       anubhutiv-test/test-unsloth-anubhutiv:/workspace/Platform
#   kubectl cp plugins/nemo-customizer/devops/init-gpu-pod.sh \
#       anubhutiv-test/test-unsloth-anubhutiv:/workspace/
#   kubectl exec -it -n anubhutiv-test test-unsloth-anubhutiv -- \
#       bash /workspace/init-gpu-pod.sh

set -euo pipefail

WORKSPACE_DIR="/workspace"
PLATFORM_DIR="${WORKSPACE_DIR}/Platform"
HOST_VENV="${WORKSPACE_DIR}/.venv-host"
UNSLOTH_VENV="${WORKSPACE_DIR}/.venv-unsloth"

log() { printf '\n[%s] %s\n' "$(date +%H:%M:%S)" "$*" >&2; }

# ───────────────────────────────────────────────────────────────────────
# 1. OS deps + Python 3.11 + uv
# ───────────────────────────────────────────────────────────────────────
if ! command -v python3.11 >/dev/null 2>&1; then
    log "Installing OS prerequisites"
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y --no-install-recommends \
        curl ca-certificates git \
        build-essential pkg-config \
        software-properties-common \
        vim less jq

    log "Installing Python 3.11 via deadsnakes PPA"
    add-apt-repository -y ppa:deadsnakes/ppa
    apt-get update
    apt-get install -y --no-install-recommends \
        python3.11 python3.11-venv python3.11-dev
else
    log "Python 3.11 already present — skipping OS deps"
fi

if ! command -v uv >/dev/null 2>&1 && [[ ! -x "${HOME}/.local/bin/uv" ]]; then
    log "Installing uv"
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="${HOME}/.local/bin:${PATH}"
uv --version

# ───────────────────────────────────────────────────────────────────────
# 2. Locate the Platform repo
# ───────────────────────────────────────────────────────────────────────
if [[ ! -d "${PLATFORM_DIR}" ]]; then
    log "ERROR: ${PLATFORM_DIR} not found."
    echo "From your mac, run:" >&2
    echo "  kubectl cp /Users/anubhutiv/workspace/Platform \\" >&2
    echo "      anubhutiv-test/test-unsloth-anubhutiv:/workspace/Platform" >&2
    echo "Or git-clone the repo into /workspace/Platform inside the pod." >&2
    exit 1
fi
log "Found Platform repo at ${PLATFORM_DIR}"

# ───────────────────────────────────────────────────────────────────────
# 3. Host venv — nemo CLI + customizer plugin (slim; no backend deps)
# ───────────────────────────────────────────────────────────────────────
if [[ ! -x "${HOST_VENV}/bin/python" ]]; then
    log "Creating host venv at ${HOST_VENV}"
    uv venv "${HOST_VENV}" --python 3.11
fi
# shellcheck disable=SC1091
source "${HOST_VENV}/bin/activate"
export VIRTUAL_ENV="${HOST_VENV}"

log "Installing platform + customizer plugin (editable) into host venv"
uv pip install \
    -e "${PLATFORM_DIR}/packages/nemo_platform" \
    -e "${PLATFORM_DIR}/packages/nemo_platform_plugin" \
    -e "${PLATFORM_DIR}/plugins/nemo-customizer"

# Symlink `nemo` into /usr/local/bin so subsequent `kubectl exec` shells
# (which do not source bashrc and do not inherit this script's PATH) can
# find the binary without the user activating the host venv manually.
log "Symlinking nemo into /usr/local/bin/nemo"
ln -sf "${HOST_VENV}/bin/nemo" /usr/local/bin/nemo

# Persist the host venv on PATH for every interactive shell in the pod.
# Belt-and-braces with the symlink — also makes `python`, `pip`, etc.
# resolve to the host venv when not explicitly activated.
cat > /etc/profile.d/nemo-customizer.sh <<EOF
# Added by init-gpu-pod.sh — put the customizer host venv first on PATH.
export PATH="${HOST_VENV}/bin:\${PATH}"
export UNSLOTH_VENV="${UNSLOTH_VENV}"
EOF
chmod 0644 /etc/profile.d/nemo-customizer.sh

log "Verifying CLI wiring"
nemo customizer --help
nemo customizer finetune run --help | head -40 || true

# ───────────────────────────────────────────────────────────────────────
# 4. GPU sanity check
# ───────────────────────────────────────────────────────────────────────
log "GPU sanity check (nvidia-smi)"
nvidia-smi || { echo "nvidia-smi failed; aborting"; exit 1; }

# ───────────────────────────────────────────────────────────────────────
# 5. Unsloth venv — created here if missing (the PLUGIN does not do this)
# ───────────────────────────────────────────────────────────────────────
if [[ ! -x "${UNSLOTH_VENV}/bin/python" ]]; then
    log "Creating unsloth venv at ${UNSLOTH_VENV} (does not exist)"
    uv venv "${UNSLOTH_VENV}" --python 3.11
    log "Installing nemo-customizer-plugin[unsloth] into ${UNSLOTH_VENV} (multi-GB; several minutes on first run)"
    uv pip install --python "${UNSLOTH_VENV}/bin/python" \
        -e "${PLATFORM_DIR}/plugins/nemo-customizer[unsloth]"
else
    log "Unsloth venv already exists at ${UNSLOTH_VENV} — reusing"
fi

log "Probing unsloth venv health"
nemo customizer doctor --backend unsloth --venv "${UNSLOTH_VENV}"

# ───────────────────────────────────────────────────────────────────────
# 6. Smoke test against the existing venv
# ───────────────────────────────────────────────────────────────────────
log "Running smoke test: nemo customizer finetune run --venv ${UNSLOTH_VENV} ..."
nemo customizer finetune run \
    --venv "${UNSLOTH_VENV}" \
    --backend unsloth \
    --training-type sft \
    --gpus 0

log "Smoke test complete. Inspect the JSON result printed above."
echo
echo "Shell setup for new sessions:"
echo "  - \`nemo\` is symlinked into /usr/local/bin, so any \`kubectl exec\` shell can call it directly."
echo "  - \`\$UNSLOTH_VENV\` is exported via /etc/profile.d/nemo-customizer.sh for interactive shells."
echo "  - If you bypass /etc/profile (e.g. \`bash --noprofile\`), set it manually:"
echo "      export UNSLOTH_VENV=${UNSLOTH_VENV}"
echo
echo "Next steps:"
echo "  - Customize a run:"
echo "      nemo customizer finetune run --venv \$UNSLOTH_VENV \\"
echo "          --backend unsloth --training-type sft \\"
echo "          --model unsloth/llama-3-8b-bnb-4bit --max-steps 10 --gpus 0"
echo
echo "  - Try a stub backend (expect NotImplementedError):"
echo "      nemo customizer finetune run --venv \$UNSLOTH_VENV --backend automodel --training-type sft"
echo
echo "  - Test the no-venv negative path (expect actionable RuntimeError):"
echo "      nemo customizer finetune run --backend unsloth --training-type sft"
