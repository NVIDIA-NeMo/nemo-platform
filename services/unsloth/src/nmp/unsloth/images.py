# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Docker image resolution for nmp-unsloth job steps.

Mirrors :mod:`nmp.automodel.images`. Consumed by the compiler in
:mod:`nmp.unsloth.app.jobs.compiler` (and its training sub-compiler) to
stamp the right image refs onto each container step.

Unsloth ships a **single** image, ``nmp-unsloth-training``, used by all four
steps (file_io, model_entity, training) — the CPU task steps reuse the training
image rather than a separate ``nmp-unsloth-tasks`` build. Override the whole
image via ``NMP_UNSLOTH_TRAINING_IMAGE``.
"""

from __future__ import annotations

from nmp.customization_common.service.images import resolve_qualified_image
from nmp.unsloth.config import config

BASE_IMAGE_NAME = "nmp-unsloth-base"
TASKS_IMAGE_NAME = "nmp-unsloth-tasks"
TRAINING_IMAGE_NAME = "nmp-unsloth-training"

# Must match ENTRYPOINT in Dockerfile.nmp-unsloth-{tasks,training}.
# Job specs must set this explicitly: Docker API ``create()`` replaces the
# image entrypoint when the platform passes ``entrypoint=[]``.
UNSLOTH_PYTHON_ENTRYPOINT = ["/opt/venv/bin/python"]


def get_unsloth_qualified_image(name: str, override: str | None = None) -> str:
    """Resolve a job step image reference (see ``resolve_qualified_image``)."""
    return resolve_qualified_image(name, override, config.image_registry)


def get_tasks_image() -> str:
    """CPU task steps (file_io, model_entity).

    Unsloth ships a single image, so the CPU task steps reuse the
    ``nmp-unsloth-training`` image rather than a separate tasks image.
    """
    return get_training_image()


def get_training_image() -> str:
    """GPU training step."""
    return get_unsloth_qualified_image(TRAINING_IMAGE_NAME, config.training_image)
