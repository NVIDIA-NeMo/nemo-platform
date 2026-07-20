# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""nmp-customizer-tasks image import smoke tests.

Built as part of the docker-bake.hcl bake group (smoke-test stage) and run
on a CPU runner — no GPU hardware required.

Two failure classes are caught at .so load time, before any GPU device is touched:

  ModuleNotFoundError  — package missing from the image (e.g. excluded from
                         a tar layer without a compensating COPY command)

  ImportError          — CUDA extension .so has an undefined symbol; the wheel
                         was compiled against a different PyTorch version than
                         the one installed (ABI mismatch)
"""

import pytest


@pytest.mark.smoke_nmp_customizer_tasks
def test_torch_importable():
    import torch  # noqa: F401


@pytest.mark.smoke_nmp_customizer_tasks
def test_transformers_importable():
    import transformers  # noqa: F401


@pytest.mark.smoke_nmp_customizer_tasks
def test_accelerate_importable():
    import accelerate  # noqa: F401


@pytest.mark.smoke_nmp_customizer_tasks
def test_mamba_ssm_importable():
    import mamba_ssm  # noqa: F401


@pytest.mark.smoke_nmp_customizer_tasks
def test_causal_conv1d_importable():
    import causal_conv1d  # noqa: F401


@pytest.mark.smoke_nmp_customizer_tasks
def test_nmp_customizer_tasks_importable():
    from nmp.core.models.sidecars.adapters.main import run as lora_sidecar_run  # noqa: F401
    from nmp.core.models.tasks.model_spec import __main__ as model_spec_main  # noqa: F401
    from nmp.customization_common.tasks import file_io  # noqa: F401
    from nmp.customization_common.tasks.file_io import __main__ as file_io_main  # noqa: F401
    from nmp.customization_common.tasks.model_entity import __main__ as model_entity_main  # noqa: F401
