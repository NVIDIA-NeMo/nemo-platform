# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Docker image publisher for NAT agents.

Tags a locally-built image and pushes it to a remote registry.
Assumes the environment already has ``docker login`` credentials for the
target registry.
"""

from __future__ import annotations

import logging

import typer

logger = logging.getLogger(__name__)


def docker_push(
    *,
    local_tag: str,
    registry: str,
    push_tag: str | None = None,
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
        typer.Exit: On tag or push failure.
    """
    try:
        from python_on_whales import docker  # type: ignore[unresolved-import]
    except ImportError:
        typer.echo(
            "Error: 'python-on-whales' is required for publishing images.  "
            "Install it with:  pip install 'nemo-agents-plugin[container]'",
            err=True,
        )
        raise typer.Exit(code=1)

    if push_tag is None:
        # Strip any leading/trailing slashes from the registry.
        push_tag = f"{registry.rstrip('/')}/{local_tag}"

    typer.echo(f"Tagging {local_tag} -> {push_tag}")
    try:
        docker.tag(local_tag, push_tag)
    except Exception as exc:
        typer.echo(f"Docker tag failed: {exc}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Pushing {push_tag} ...")
    try:
        docker.push(push_tag)
    except Exception as exc:
        typer.echo(f"Docker push failed: {exc}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Successfully pushed {push_tag}")
    return push_tag
