# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Docker image resolution for nmp-unsloth job steps.

Mirrors :mod:`nmp.automodel.images`. Consumed by the compiler in
:mod:`nmp.unsloth.app.jobs.compiler` (and its training sub-compiler) to
stamp the right image refs onto each container step.

Today we ship **one** image, ``nmp-unsloth-training``, used by all four
steps (file_io, model_entity, training). Production environments that
want a leaner CPU image for file_io / model_entity can publish a separate
``nmp-unsloth-tasks`` and point ``NMP_UNSLOTH_TASKS_IMAGE`` at it.
"""

from __future__ import annotations

from nemo_platform_plugin.config import get_platform_config
from nemo_platform_plugin.jobs.image import get_qualified_image
from nmp.unsloth.config import config

BASE_IMAGE_NAME = "nmp-unsloth-base"
TASKS_IMAGE_NAME = "nmp-unsloth-tasks"
TRAINING_IMAGE_NAME = "nmp-unsloth-training"

# Must match ENTRYPOINT in Dockerfile.nmp-unsloth-{tasks,training}.
# Job specs must set this explicitly: Docker API ``create()`` replaces the
# image entrypoint when the platform passes ``entrypoint=[]``.
UNSLOTH_PYTHON_ENTRYPOINT = ["/opt/venv/bin/python"]


def get_unsloth_qualified_image(name: str, override: str | None = None) -> str:
    """Resolve a job step image reference.

    Args:
        name: Image repository name under the registry (e.g. ``nmp-unsloth-tasks``).
        override: Full image ref from ``NMP_UNSLOTH_TASKS_IMAGE`` /
            ``NMP_UNSLOTH_TRAINING_IMAGE``.

    Returns:
        Fully qualified image (``{registry}/{name}:{tag}``) unless ``override`` is set.
    """
    if override:
        return override

    platform_config = get_platform_config()
    registry = config.image_registry or platform_config.image_registry
    return get_qualified_image(name, registry=registry)


def get_tasks_image() -> str:
    """CPU task steps (file_io, model_entity).

    When no explicit ``NMP_UNSLOTH_TASKS_IMAGE`` is set we reuse the
    training image — it has the platform glue (``nmp-common`` SDK +
    ``nemo-platform``) needed by file_io / model_entity in addition to
    the ML stack. Override at deploy time once a leaner image exists.
    """
    if config.tasks_image:
        return get_unsloth_qualified_image(TASKS_IMAGE_NAME, config.tasks_image)
    return get_training_image()


def get_training_image() -> str:
    """GPU training step."""
    return get_unsloth_qualified_image(TRAINING_IMAGE_NAME, config.training_image)
