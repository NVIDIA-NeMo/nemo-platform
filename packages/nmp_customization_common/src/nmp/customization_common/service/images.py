# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared Docker image resolution for customization job steps.

Each backend keeps its own ``get_training_image``; CPU task steps share
``nmp-customizer-tasks`` via :func:`get_customizer_tasks_image`.
"""

from __future__ import annotations

from nemo_platform_plugin.config import get_platform_config
from nemo_platform_plugin.jobs.image import get_qualified_image
from nmp.customization_common.config import config as customization_common_config

CUSTOMIZER_TASKS_IMAGE_NAME = "nmp-customizer-tasks"

# Must match ENTRYPOINT in docker/Dockerfile.nmp-customizer-tasks.
CUSTOMIZER_PYTHON_ENTRYPOINT = ["/opt/venv/bin/python"]


def resolve_qualified_image(name: str, override: str | None, image_registry: str | None) -> str:
    """Resolve a job step image reference.

    Args:
        name: Image repository name under the registry (e.g. ``nmp-<svc>-tasks``).
        override: Full image ref (e.g. from ``NMP_<SVC>_TASKS_IMAGE``); returned verbatim when set.
        image_registry: Backend ``config.image_registry``; falls back to the platform registry.

    Returns:
        Fully qualified image (``{registry}/{name}:{tag}``) unless ``override`` is set.
    """
    if override:
        return override

    platform_config = get_platform_config()
    registry = image_registry or platform_config.image_registry
    return get_qualified_image(name, registry=registry)


def get_customizer_tasks_image(
    *,
    backend_override: str | None = None,
    image_registry: str | None = None,
) -> str:
    """Resolve the shared CPU tasks image for customization job steps.

    Precedence: ``NMP_CUSTOMIZER_TASKS_IMAGE`` (global), then the
    per-backend ``tasks_image`` override (e.g. ``NMP_AUTOMODEL_TASKS_IMAGE``),
    then ``{registry}/nmp-customizer-tasks:{tag}``.
    """
    override = customization_common_config.tasks_image or backend_override
    return resolve_qualified_image(CUSTOMIZER_TASKS_IMAGE_NAME, override, image_registry)
