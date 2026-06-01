# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""GPU task image import smoke tests.

Built as part of the docker-gpu bake group (smoke-test stage) and run on a CPU
runner — no GPU hardware required.

Two failure classes are caught at .so load time, before any GPU device is touched:

  ModuleNotFoundError  — package missing from the image (e.g. excluded from
                         a tar layer without a compensating COPY command)

  ImportError          — CUDA extension .so has an undefined symbol; the wheel
                         was compiled against a different PyTorch version than
                         the one installed (ABI mismatch)
"""

import pytest

pytestmark = pytest.mark.smoke_gpu_tasks


def test_torch_importable():
    import torch  # noqa: F401


def test_transformers_importable():
    import transformers  # noqa: F401


def test_vllm_importable():
    import vllm  # noqa: F401


def test_mamba_ssm_importable():
    import mamba_ssm  # noqa: F401


def test_causal_conv1d_importable():
    import causal_conv1d  # noqa: F401


def test_nemo_safe_synthesizer_plugin_importable():
    import nemo_safe_synthesizer_plugin.service  # noqa: F401


def test_nmp_customizer_importable():
    import nmp.customizer  # noqa: F401
