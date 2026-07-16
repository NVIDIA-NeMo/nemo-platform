# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Docker image resolution for nmp-rl job steps.

Unlike unsloth (single image), nmp-rl follows the automodel split: a heavy
``nmp-rl-training`` image for the GPU training step and the shared
``nmp-customizer-tasks`` image for CPU file_io / model_entity steps.
"""

from __future__ import annotations

from nmp.customization_common.service.images import (
    CUSTOMIZER_PYTHON_ENTRYPOINT,
    get_customizer_tasks_image,
    resolve_qualified_image,
)
from nmp.rl.config import config

BASE_IMAGE_NAME = "nmp-rl-base"
TRAINING_IMAGE_NAME = "nmp-rl-training"

RL_PYTHON_ENTRYPOINT = CUSTOMIZER_PYTHON_ENTRYPOINT

FILE_IO_TASK_COMMAND = [
    "-m",
    "nmp.customization_common.tasks.file_io",
    "--service-source",
    "rl",
    "--service-name",
    "rl",
]
MODEL_ENTITY_TASK_COMMAND = [
    "-m",
    "nmp.customization_common.tasks.model_entity",
    "--service-name",
    "rl",
]


def get_rl_qualified_image(name: str, override: str | None = None) -> str:
    """Resolve a job step image reference (see ``resolve_qualified_image``)."""
    return resolve_qualified_image(name, override, config.image_registry)


def get_tasks_image() -> str:
    """CPU task steps (file_io, model_entity) — shared ``nmp-customizer-tasks`` image."""
    return get_customizer_tasks_image(backend_override=config.tasks_image, image_registry=config.image_registry)


def get_training_image() -> str:
    """GPU training step — NGC + NeMo-RL + Ray."""
    return get_rl_qualified_image(TRAINING_IMAGE_NAME, config.training_image)
