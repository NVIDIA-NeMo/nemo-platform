# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""nmp-automodel image import smoke tests.

Built as part of the docker-bake.hcl bake group (smoke-test stage) and run
on a CPU runner — no GPU hardware required.

Two failure classes are caught at .so load time, before any GPU device is touched:

  ModuleNotFoundError  — package missing from the image (e.g. excluded from
                         a tar layer without a compensating COPY command)

  ImportError          — CUDA extension .so has an undefined symbol; the wheel
                         was compiled against a different PyTorch version than
                         the one installed (ABI mismatch)
"""

import sys
from importlib.util import find_spec
from pathlib import Path

import pytest


@pytest.mark.smoke_nmp_automodel_tasks
@pytest.mark.smoke_nmp_automodel_training
def test_torch_importable():
    import torch  # noqa: F401


@pytest.mark.smoke_nmp_automodel_tasks
@pytest.mark.smoke_nmp_automodel_training
def test_transformers_importable():
    import transformers  # noqa: F401


@pytest.mark.smoke_nmp_automodel_tasks
@pytest.mark.smoke_nmp_automodel_training
def test_mamba_ssm_importable():
    import mamba_ssm  # noqa: F401


@pytest.mark.smoke_nmp_automodel_tasks
@pytest.mark.smoke_nmp_automodel_training
def test_causal_conv1d_importable():
    import causal_conv1d  # noqa: F401


@pytest.mark.smoke_nmp_automodel_tasks
@pytest.mark.smoke_nmp_automodel_training
def test_bitsandbytes_importable():
    import bitsandbytes  # noqa: F401


@pytest.mark.smoke_nmp_automodel_tasks
@pytest.mark.smoke_nmp_automodel_training
@pytest.mark.parametrize("module", ["av", "cv2"])
def test_unused_media_packages_removed(module: str):
    assert find_spec(module) is None


@pytest.mark.smoke_nmp_automodel_tasks
@pytest.mark.smoke_nmp_automodel_training
@pytest.mark.parametrize("directory", ["av.libs", "opencv_python.libs", "opencv_python_headless.libs"])
def test_unused_media_shared_libraries_removed(directory: str):
    for entry in sys.path:
        if entry.endswith(("site-packages", "dist-packages")):
            assert not (Path(entry) / directory).exists()


@pytest.mark.smoke_nmp_automodel_tasks
def test_nmp_automodel_tasks_importable():
    from nmp.automodel.tasks import file_io  # noqa: F401
    from nmp.automodel.tasks.model_entity import __main__ as model_entity_main  # noqa: F401
    from nmp.core.models.tasks.model_spec import __main__ as model_spec_main  # noqa: F401


@pytest.mark.smoke_nmp_automodel_training
def test_nmp_automodel_training_importable():
    import nemo_automodel  # noqa: F401
    from nmp.automodel.tasks.training import __main__ as training_main  # noqa: F401
