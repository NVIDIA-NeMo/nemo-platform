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

from pathlib import Path

import pytest
from file_removals import assert_file_patterns_absent, read_file_patterns
from python_package_versions import assert_python_package_min_versions

BASE_FILE_REMOVALS = (Path("/smoke_test/removals/files/base/pytorch-ngc-common.txt"),)
FINAL_FILE_REMOVALS = Path("/smoke_test/removals/files/final/customizer-codecs.txt")
SOUNDFILE_FILE_REMOVALS = {
    "/opt/venv/lib/python3.*/site-packages/_soundfile_data/libsndfile_*.so",
    "/opt/venv/lib/python3.*/site-packages/soundfile.py",
}
DALI_FILE_REMOVALS = {
    "/usr/local/lib/python3.12/dist-packages/nvidia/dali",
    "/usr/local/lib/python3.12/dist-packages/nvidia_dali_cuda130-*.dist-info",
}
MINIMUM_PYTHON_PACKAGE_VERSIONS = {
    "bitsandbytes": "0.49.2",
    "mamba-ssm": "2.3.0",
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
    patterns = read_file_patterns(FINAL_FILE_REMOVALS)
    assert SOUNDFILE_FILE_REMOVALS.issubset(patterns)
    assert_file_patterns_absent(patterns)


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
def test_dali_files_removed():
    patterns = [
        pattern
        for pattern in read_file_patterns(*BASE_FILE_REMOVALS)
        if "/nvidia/dali" in pattern or "nvidia_dali_cuda130" in pattern
    ]
    assert DALI_FILE_REMOVALS.issubset(patterns)
    assert_file_patterns_absent(patterns)
