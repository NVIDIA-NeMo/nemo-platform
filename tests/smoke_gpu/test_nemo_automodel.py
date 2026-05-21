# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""NeMo Automodel image import smoke tests.

Built as part of the nmp-automodel docker bake group (smoke-test stage) and run
on a CPU runner - no GPU hardware required.
"""

import pytest


def test_torch_importable():
    import torch  # noqa: F401


def test_transformers_importable():
    import transformers  # noqa: F401


def test_mamba_ssm_importable():
    import mamba_ssm  # noqa: F401


def test_causal_conv1d_importable():
    import causal_conv1d  # noqa: F401


def test_bitsandbytes_importable():
    import bitsandbytes  # noqa: F401


@pytest.mark.smoke_nmp_automodel_tasks
def test_nmp_automodel_tasks_importable():
    from nmp.automodel.tasks import file_io  # noqa: F401
    from nmp.automodel.tasks.model_entity import __main__ as model_entity_main  # noqa: F401
    from nmp.core.models.tasks.model_spec import __main__ as model_spec_main  # noqa: F401


@pytest.mark.smoke_nmp_automodel_training
def test_nmp_automodel_training_importable():
    import nemo_automodel  # noqa: F401
    from nmp.automodel.tasks.training import __main__ as training_main  # noqa: F401
