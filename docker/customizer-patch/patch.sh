#!/bin/bash

set -euxo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

INSTALLATION_TARGET=${INSTALLATION_TARGET:-"/opt/Automodel"}

# Add HFCheckpointingMixin to NemotronHForCausalLM (from commit 07b0700, without transformers v5 bump)
patch ${INSTALLATION_TARGET}/nemo_automodel/components/models/nemotron_v3/model.py ${SCRIPT_DIR}/model.py.diff

# From https://github.com/NVIDIA-NeMo/Automodel/pull/1365/changes.
# File nemo_automodel/components/moe/experts.py was layers.py in old code.
patch ${INSTALLATION_TARGET}/nemo_automodel/components/moe/layers.py ${SCRIPT_DIR}/layers.py.diff
