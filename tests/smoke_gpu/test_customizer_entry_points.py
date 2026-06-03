# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Customizer task entry-point import smoke tests.

Exercises the *actual* task modules — not just the top-level package — so
that transitive dependency failures (e.g. a missing ``typing_extensions``
pulled in via ``nemo_platform`` SDK) are caught at image-build time.

Each test is marked with every image marker whose Dockerfile ships that
module, so the single file is reused across all smoke-test stages.
"""

import pytest

# ---------------------------------------------------------------------------
# Training entry point — present in every customizer / gpu-tasks image
# ---------------------------------------------------------------------------


@pytest.mark.smoke_customizer_rl
@pytest.mark.smoke_customizer_tasks
@pytest.mark.smoke_gpu_tasks
def test_training_entry_point_importable():
    """Import nmp.customizer.tasks.training and its transitive deps.

    The training __main__ pulls in runner → NMPJobContext → nemo_platform SDK →
    typing_extensions.  A shallow ``import nmp.customizer`` never reaches this
    code path.
    """
    import nmp.customizer.tasks.training  # noqa: F401


# ---------------------------------------------------------------------------
# model_entity / file_io — present in customizer-tasks and gpu-tasks images
# ---------------------------------------------------------------------------


@pytest.mark.smoke_customizer_tasks
@pytest.mark.smoke_gpu_tasks
def test_model_entity_entry_point_importable():
    """Verify the model_entity task module and its transitive deps are present."""
    import nmp.customizer.tasks.model_entity  # noqa: F401


@pytest.mark.smoke_customizer_tasks
@pytest.mark.smoke_gpu_tasks
def test_file_io_entry_point_importable():
    """Verify the file_io task module and its transitive deps are present."""
    import nmp.customizer.tasks.file_io  # noqa: F401
