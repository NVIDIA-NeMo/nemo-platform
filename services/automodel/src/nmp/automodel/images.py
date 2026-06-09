# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Docker image resolution for nmp-automodel job steps."""

from __future__ import annotations

from nemo_platform_plugin.config import get_platform_config
from nemo_platform_plugin.jobs.image import get_qualified_image
from nmp.automodel.config import config

BASE_IMAGE_NAME = "nmp-automodel-base"
TASKS_IMAGE_NAME = "nmp-automodel-tasks"
TRAINING_IMAGE_NAME = "nmp-automodel-training"

# Must match ENTRYPOINT in Dockerfile.nmp-automodel-{tasks,training}.
# Job specs must set this explicitly: Docker API create() replaces the image
# entrypoint when the platform passes entrypoint=[].
AUTOMODEL_PYTHON_ENTRYPOINT = ["/opt/venv/bin/python"]


def get_automodel_qualified_image(name: str, override: str | None = None) -> str:
    """Resolve a job step image reference.

    Args:
        name: Image repository name under the registry (e.g. ``nmp-automodel-tasks``).
        override: Full image ref from ``NMP_AUTOMODEL_TASKS_IMAGE`` / ``NMP_AUTOMODEL_TRAINING_IMAGE``.

    Returns:
        Fully qualified image (``{registry}/{name}:{tag}``) unless ``override`` is set.
    """
    if override:
        return override

    platform_config = get_platform_config()
    registry = config.image_registry or platform_config.image_registry
    return get_qualified_image(name, registry=registry)


def get_tasks_image() -> str:
    """CPU task steps (file_io, model_entity)."""
    return get_automodel_qualified_image(TASKS_IMAGE_NAME, config.tasks_image)


def get_training_image() -> str:
    """GPU training step."""
    return get_automodel_qualified_image(TRAINING_IMAGE_NAME, config.training_image)
