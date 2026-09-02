# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Docker image publisher for NAT agents.

Tags a locally-built image and pushes it to a remote registry.
Assumes the environment already has ``docker login`` credentials for the
target registry.
"""

from __future__ import annotations

import logging

from nemo_agents_plugin.container.builder import ProgressCallback, emit_progress
from nemo_agents_plugin.container.errors import ContainerToolingUnavailableError, ImagePublishError

logger = logging.getLogger(__name__)


def docker_push(
    *,
    local_tag: str,
    registry: str,
    push_tag: str | None = None,
    source_ref: str | None = None,
    on_progress: ProgressCallback | None = None,
) -> str:
    """Tag a local Docker image and push it to a remote registry.

    Args:
        local_tag: The locally-built image tag (e.g. ``"my-agent:1.0"``), used
            to compute the default *push_tag* and for progress messages.
        registry: Remote registry URL (e.g. ``"nvcr.io/my-org"``).
        push_tag: Fully-qualified remote tag.  When ``None``, computed as
            ``<registry>/<local_tag>``.
        source_ref: What ``docker tag`` actually reads from — an immutable
            image ID (see :func:`~nemo_agents_plugin.container.builder.resolve_image_id`),
            when the caller has one. Falls back to *local_tag*, which is a
            mutable, daemon-global name a concurrent build can rebind between
            this job's build and its push.

    Returns:
        The remote image tag that was pushed.

    Raises:
        ContainerToolingUnavailableError: When python-on-whales is missing.
        ImagePublishError: On tag or push failure.
    """
    try:
        from python_on_whales import docker
    except ImportError as exc:
        raise ContainerToolingUnavailableError("publishing images") from exc

    if push_tag is None:
        # Strip any leading/trailing slashes from the registry.
        push_tag = f"{registry.rstrip('/')}/{local_tag}"

    tag_source = source_ref or local_tag
    emit_progress(on_progress, f"Tagging {tag_source} -> {push_tag}")
    try:
        docker.tag(tag_source, push_tag)
    except Exception as exc:
        raise ImagePublishError(f"Docker tag failed: {exc}") from exc

    emit_progress(on_progress, f"Pushing {push_tag} ...")
    try:
        docker.push(push_tag)
    except Exception as exc:
        raise ImagePublishError(f"Docker push failed: {exc}") from exc

    emit_progress(on_progress, f"Successfully pushed {push_tag}")
    return push_tag
