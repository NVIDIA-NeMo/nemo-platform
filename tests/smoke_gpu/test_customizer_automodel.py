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

from glob import glob

import pytest
from python_package_versions import assert_python_package_min_versions

SOUNDFILE_PATTERNS = (
    "/opt/venv/lib/python3.*/site-packages/_soundfile_data/libsndfile_*.so",
    # The shim is removed with its payload; see the removals file for why keeping it is
    # worse than not shipping soundfile at all.
    "/opt/venv/lib/python3.*/site-packages/soundfile.py",
)
MINIMUM_PYTHON_PACKAGE_VERSIONS = {
    "bitsandbytes": "0.49.2",
    "mamba-ssm": "2.3.0",
    "nvidia-dali-cuda130": "2.2.0",
    "wandb": "0.28.2",
}


@pytest.mark.smoke_nmp_automodel_training
def test_python_package_min_versions():
    assert_python_package_min_versions(MINIMUM_PYTHON_PACKAGE_VERSIONS)


@pytest.mark.smoke_nmp_automodel_training
def test_torch_importable():
    import torch  # noqa: F401


@pytest.mark.smoke_nmp_automodel_training
def test_transformers_importable():
    import transformers  # noqa: F401


@pytest.mark.smoke_nmp_automodel_training
def test_mamba_ssm_importable():
    import mamba_ssm  # noqa: F401


@pytest.mark.smoke_nmp_automodel_training
def test_causal_conv1d_importable():
    import causal_conv1d  # noqa: F401


@pytest.mark.smoke_nmp_automodel_training
def test_bitsandbytes_importable():
    import bitsandbytes  # noqa: F401


@pytest.mark.smoke_nmp_automodel_training
def test_nmp_automodel_training_importable():
    import nemo_automodel  # noqa: F401
    from nmp.automodel.tasks.training import __main__ as training_main  # noqa: F401


@pytest.mark.smoke_nmp_automodel_training
def test_soundfile_libsndfile_removed():
    remaining = sorted(path for pattern in SOUNDFILE_PATTERNS for path in glob(pattern))
    assert remaining == [], f"file cleanup left scanner-visible libsndfile files: {remaining}"


@pytest.mark.smoke_nmp_automodel_training
def test_transformers_audio_backend_probe_is_off():
    """The payload and its shim must be removed together.

    ``transformers.audio_utils`` runs ``if is_soundfile_available(): import soundfile``, and
    that probe is ``find_spec("soundfile")`` -- file presence, not loadability. Removing only
    the codec leaves the probe answering yes for a backend that then fails to dlopen, which
    breaks ``from transformers import AutoProcessor`` and everything importing through it.
    """
    from transformers.utils.import_utils import is_soundfile_available

    assert not is_soundfile_available()


@pytest.mark.smoke_nmp_automodel_training
def test_dali_still_importable_after_file_cleanup():
    import importlib.metadata

    import nvidia.dali  # noqa: F401

    assert importlib.metadata.version("nvidia-dali-cuda130")
