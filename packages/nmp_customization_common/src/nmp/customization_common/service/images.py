# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared Docker image resolution for customization job steps.

Each backend keeps its own image-name constants and ``get_tasks_image`` /
``get_training_image`` (their fallback behavior differs); this module holds the
common registry-resolution logic.
"""

from __future__ import annotations

from nemo_platform_plugin.config import get_platform_config
from nemo_platform_plugin.jobs.image import get_qualified_image


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
