# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Docker image resolution for nmp-rl job steps.

Unlike unsloth (single image), nmp-rl follows the automodel split: a heavy
``nmp-rl-training`` image (NGC + NeMo-RL + Ray) for the GPU training step and a
lighter ``nmp-rl-tasks`` image for the CPU file_io / model_entity steps. Both
build on ``nmp-rl-base``. Override via ``NMP_RL_TRAINING_IMAGE`` /
``NMP_RL_TASKS_IMAGE``.
"""

from __future__ import annotations

from nmp.customization_common.service.images import resolve_qualified_image
from nmp.rl.config import config

BASE_IMAGE_NAME = "nmp-rl-base"
TASKS_IMAGE_NAME = "nmp-rl-tasks"
TRAINING_IMAGE_NAME = "nmp-rl-training"

# Must match ENTRYPOINT in Dockerfile.nmp-rl-{tasks,training}. Job specs set this
# explicitly: Docker API create() replaces the image entrypoint when passed [].
RL_PYTHON_ENTRYPOINT = ["/opt/venv/bin/python"]


def get_rl_qualified_image(name: str, override: str | None = None) -> str:
    """Resolve a job step image reference (see ``resolve_qualified_image``)."""
    return resolve_qualified_image(name, override, config.image_registry)


def get_tasks_image() -> str:
    """CPU task steps (file_io, model_entity) — lighter image, no NeMo-RL/vLLM."""
    return get_rl_qualified_image(TASKS_IMAGE_NAME, config.tasks_image)


def get_training_image() -> str:
    """GPU training step — NGC + NeMo-RL + Ray."""
    return get_rl_qualified_image(TRAINING_IMAGE_NAME, config.training_image)
