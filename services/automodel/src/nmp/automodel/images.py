# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Docker image resolution for nmp-automodel job steps."""

from __future__ import annotations

from nmp.automodel.config import config
from nmp.customization_common.service.images import resolve_qualified_image

BASE_IMAGE_NAME = "nmp-automodel-base"
TASKS_IMAGE_NAME = "nmp-automodel-tasks"
TRAINING_IMAGE_NAME = "nmp-automodel-training"

# Must match ENTRYPOINT in docker/automodel/Dockerfile.nmp-automodel-{tasks,training}.
# Job specs must set this explicitly: Docker API create() replaces the image
# entrypoint when the platform passes entrypoint=[].
AUTOMODEL_PYTHON_ENTRYPOINT = ["/opt/venv/bin/python"]


def get_automodel_qualified_image(name: str, override: str | None = None) -> str:
    """Resolve a job step image reference (see ``resolve_qualified_image``)."""
    return resolve_qualified_image(name, override, config.image_registry)


def get_tasks_image() -> str:
    """CPU task steps (file_io, model_entity)."""
    return get_automodel_qualified_image(TASKS_IMAGE_NAME, config.tasks_image)


def get_training_image() -> str:
    """GPU training step."""
    return get_automodel_qualified_image(TRAINING_IMAGE_NAME, config.training_image)
