# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Docker image publisher for NAT agents.

Tags a locally-built image and pushes it to a remote registry.
Assumes the environment already has ``docker login`` credentials for the
target registry.
"""

from __future__ import annotations

import logging

from nemo_agents_plugin.container.builder import ProgressCallback, _progress
from nemo_agents_plugin.container.errors import ContainerToolingUnavailableError, ImagePublishError

logger = logging.getLogger(__name__)


def docker_push(
    *,
    local_tag: str,
    registry: str,
    push_tag: str | None = None,
    on_progress: ProgressCallback | None = None,
) -> str:
    """Tag a local Docker image and push it to a remote registry.

    Args:
        local_tag: The locally-built image tag (e.g. ``"my-agent:1.0"``).
        registry: Remote registry URL (e.g. ``"nvcr.io/my-org"``).
        push_tag: Fully-qualified remote tag.  When ``None``, computed as
            ``<registry>/<local_tag>``.

    Returns:
        The remote image tag that was pushed.

    Raises:
        ContainerToolingUnavailableError: When python-on-whales is missing.
        ImagePublishError: On tag or push failure.
    """
    try:
        from python_on_whales import docker  # ty: ignore[unresolved-import]
    except ImportError as exc:
        raise ContainerToolingUnavailableError("publishing images") from exc

    if push_tag is None:
        # Strip any leading/trailing slashes from the registry.
        push_tag = f"{registry.rstrip('/')}/{local_tag}"

    _progress(on_progress, f"Tagging {local_tag} -> {push_tag}")
    try:
        docker.tag(local_tag, push_tag)
    except Exception as exc:
        raise ImagePublishError(f"Docker tag failed: {exc}") from exc

    _progress(on_progress, f"Pushing {push_tag} ...")
    try:
        docker.push(push_tag)
    except Exception as exc:
        raise ImagePublishError(f"Docker push failed: {exc}") from exc

    _progress(on_progress, f"Successfully pushed {push_tag}")
    return push_tag
