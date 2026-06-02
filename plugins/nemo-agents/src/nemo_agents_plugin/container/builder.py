# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Docker image builder for NAT agents.

Builds a Docker image either from a pre-existing Dockerfile or by rendering
one on-the-fly via :func:`~nemo_agents_plugin.container.template.render_dockerfile`.

Uses `python-on-whales <https://github.com/gabrieldemarmiesse/python-on-whales>`_
for Docker operations so callers never need to shell out manually.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

import typer

logger = logging.getLogger(__name__)


def docker_build(
    *,
    context_dir: Path,
    dockerfile: Path | None = None,
    tag: str,
    build_args: dict[str, str] | None = None,
    platforms: list[str] | None = None,
    push: bool = False,
) -> str:
    """Build a Docker image and return the tag.

    Args:
        context_dir: Docker build context directory.
        dockerfile: Path to an existing Dockerfile.  When ``None`` the
            caller is expected to have already written a rendered Dockerfile
            into *context_dir*.
        tag: Image tag (e.g. ``"my-agent:1.0"``).
        build_args: Extra ``--build-arg`` key/value pairs forwarded to
            ``docker build``.
        platforms: ``--platform`` values forwarded to ``docker build``. Up
            to one entry — multi-arch builds via buildx are not yet
            implemented and are rejected at the CLI layer.
        push: Push the image as part of the build (single round-trip).

    Returns:
        The image tag that was built.

    Raises:
        typer.Exit: On build failure.
    """
    try:
        from python_on_whales import docker  # type: ignore[unresolved-import]
    except ImportError:
        typer.echo(
            "Error: 'python-on-whales' is required for building images.  "
            "Install it with:  pip install 'nemo-agents-plugin[container]'",
            err=True,
        )
        raise typer.Exit(code=1)

    # The plugin's Dockerfile uses BuildKit cache mounts (``RUN --mount=...``)
    # which silently fail on older daemons without ``DOCKER_BUILDKIT=1``.
    # ``setdefault`` so a user who explicitly sets ``DOCKER_BUILDKIT=0``
    # (e.g. to debug a layer) is not surprised by the override.
    os.environ.setdefault("DOCKER_BUILDKIT", "1")

    file_arg = str(dockerfile) if dockerfile else None
    typer.echo(f"Building image '{tag}' from context {context_dir} ...")
    try:
        docker.build(
            str(context_dir),
            file=file_arg,
            tags=[tag],
            build_args=build_args or {},
            platforms=platforms or None,
            push=push,
        )
    except Exception as exc:
        typer.echo(f"Docker build failed: {exc}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Successfully built {tag}")
    return tag


def build_agent_image(
    agent_config: Path,
    pyproject: Path | None = None,
    dockerfile: Path | None = None,
    tag: str | None = None,
    *,
    nat_version: str | None = None,
    base_image_url: str | None = None,
    base_image_tag: str | None = None,
    python_version: str | None = None,
    uv_version: str | None = None,
    allow_root: bool = False,
    agent_version: str | None = None,
    agent_author: str | None = None,
    template_path: str | None = None,
    skip_validation: bool = False,
    generate_ignore: bool = True,
    platforms: list[str] | None = None,
    push: bool = False,
) -> str:
    """High-level helper: validate, render (if needed), then build.

    When *dockerfile* is ``None``, a Dockerfile is rendered via the template
    module and written into a temporary file inside the build context.

    Returns:
        The Docker image tag.
    """
    from nemo_agents_plugin.container.metadata import extract_agent_metadata
    from nemo_agents_plugin.container.template import render_dockerfile, render_dockerignore, resolve_value
    from nemo_agents_plugin.container.validator import validate_agent_config

    if not skip_validation:
        result = validate_agent_config(agent_config)
        # Soft warnings (e.g. unknown workflow._type) are surfaced regardless
        # of overall validity so the operator can see them even when the
        # config is otherwise fine.  Hard errors still abort the build.
        for warn in result.warnings:
            typer.echo(f"warning: {warn}", err=True)
        if not result.valid:
            typer.echo("Agent config validation failed:", err=True)
            for err in result.errors:
                typer.echo(f"  - {err}", err=True)
            raise typer.Exit(code=1)

    if pyproject is not None and pyproject.exists():
        context_dir = pyproject.resolve().parent
    else:
        context_dir = agent_config.resolve().parent

    resolved_nat = resolve_value("nat_version", nat_version)
    resolved_python = resolve_value("python_version", python_version)
    resolved_base_url = resolve_value("base_image_url", base_image_url)
    resolved_base_tag = resolve_value("base_image_tag", base_image_tag)
    # Feed the resolved build environment into the agent_id hash so a rebuild
    # with a different toolchain (different NAT release, base image, or
    # Python) yields a distinct id, instead of silently re-tagging an
    # ABI-incompatible image with the same suffix.
    build_env_for_id = {
        "nat_version": resolved_nat,
        "python_version": resolved_python,
        "base_image_url": resolved_base_url,
        "base_image_tag": resolved_base_tag,
    }
    # Extract metadata once and thread it through both the tag computation
    # and the Dockerfile render — avoids three duplicate ``git`` subprocess
    # calls and two redundant yaml/toml parses per build.
    meta = extract_agent_metadata(
        agent_config,
        pyproject,
        agent_version=agent_version,
        agent_author=agent_author,
        build_env=build_env_for_id,
    )

    if tag is None:
        tag = _default_tag_from_meta(meta)

    build_args: dict[str, str] = {"NAT_VERSION": resolved_nat}
    if python_version:
        build_args["PYTHON_VERSION"] = python_version
    if base_image_url:
        build_args["BASE_IMAGE_URL"] = base_image_url
    if base_image_tag:
        build_args["BASE_IMAGE_TAG"] = base_image_tag

    if dockerfile is not None:
        return docker_build(
            context_dir=context_dir,
            dockerfile=dockerfile,
            tag=tag,
            build_args=build_args,
            platforms=platforms,
            push=push,
        )

    content = render_dockerfile(
        agent_config,
        pyproject,
        base_image_url=base_image_url,
        base_image_tag=base_image_tag,
        python_version=python_version,
        nat_version=nat_version,
        uv_version=uv_version,
        allow_root=allow_root,
        agent_version=agent_version,
        agent_author=agent_author,
        template_path=template_path,
        metadata=meta,
    )

    tmp_dockerfile = context_dir / "Dockerfile.generated"
    # The temp Dockerfile is auto-cleaned in ``finally``; refuse to clobber a
    # pre-existing file by the same name, since the cleanup would delete the
    # user's file along with our own.
    if tmp_dockerfile.exists():
        raise typer.Exit(_emit_refusal_error(tmp_dockerfile))
    ignore_file: Path | None = None
    # Snapshot the pre-existing ``.dockerignore`` state so the ``finally``
    # cleanup only deletes files this run actually *created*.  Without this,
    # a committed-and-checked-in plugin-managed ``.dockerignore`` (sentinel
    # header on first line, intentionally kept in the repo) would be wiped:
    # ``render_dockerignore`` regenerates plugin-managed files in place and
    # returns the path, and the cleanup below would treat that returned path
    # as a transient artifact.  Two cases the cleanup must distinguish:
    #   (a) file did NOT exist before this run -> we just created it ->
    #       safe to unlink (the user never put it there).
    #   (b) file existed before this run -> the user committed/wrote it,
    #       even if plugin-managed -> must NOT unlink.
    ignore_path = context_dir / ".dockerignore"
    ignore_pre_existed = ignore_path.exists()
    try:
        tmp_dockerfile.write_text(content, encoding="utf-8")

        if generate_ignore:
            # ``render_dockerignore`` returns ``None`` when a user-owned file
            # was preserved — keeping ``ignore_file`` None means the
            # ``finally`` clause leaves it alone.
            ignore_file = render_dockerignore(context_dir)

        return docker_build(
            context_dir=context_dir,
            dockerfile=tmp_dockerfile,
            tag=tag,
            build_args=build_args,
            platforms=platforms,
            push=push,
        )
    finally:
        tmp_dockerfile.unlink(missing_ok=True)
        if ignore_file is not None and not ignore_pre_existed:
            ignore_file.unlink(missing_ok=True)


def _emit_refusal_error(path: Path) -> int:
    """Emit a uniform refuse-to-overwrite error and return the exit code."""
    typer.echo(
        f"Error: refusing to overwrite pre-existing file {path}. Rename or remove it and re-run the package command.",
        err=True,
    )
    return 1


_TAG_NAME_INVALID = re.compile(r"[^a-z0-9._-]")
_TAG_VERSION_INVALID = re.compile(r"[^a-zA-Z0-9._-]")


def _sanitize_image_name(raw: str) -> str:
    """Coerce *raw* into a valid Docker image name component.

    Docker reference syntax requires lowercase, ``[a-z0-9]`` plus the
    separators ``.`` ``-`` ``_``; uppercase letters (legal in PEP 621
    project names like ``"HelloWorld"``) and most punctuation are
    rejected by ``docker build`` with an opaque "invalid reference
    format" error.  Lowercase, replace illegal runs with ``-``, trim
    leading/trailing separators.
    """
    if not raw:
        return "agent"
    out = _TAG_NAME_INVALID.sub("-", raw.lower())
    out = out.strip("._-")
    return out or "agent"


def _sanitize_image_tag(raw: str) -> str:
    """Coerce *raw* into a valid Docker image tag.

    PEP 440 versions legitimately contain characters Docker rejects in
    tags — ``+`` (local-version separator), ``!`` (epoch), spaces — and
    the empty string is illegal.  Replace each illegal run with ``.``
    (Docker-valid and preserves the visual delimiter intent), strip
    leading non-alphanumeric characters (Docker requires the first byte
    to be ``[a-zA-Z0-9_]``), and bound the length at the 128-char
    reference limit.
    """
    if not raw:
        return "latest"
    out = _TAG_VERSION_INVALID.sub(".", raw)
    out = re.sub(r"^[^a-zA-Z0-9_]+", "", out)
    out = out[:128]
    return out or "latest"


def _default_tag_from_meta(meta: dict[str, str]) -> str:
    """Build a default image reference from precomputed metadata.

    Format: ``{agent_name}-{agent_id}:{agent_version}``, with both
    components sanitized for the Docker reference grammar.
    """
    name = _sanitize_image_name(meta["agent_name"])
    aid = meta["agent_id"]
    version = _sanitize_image_tag(meta["agent_version"])
    return f"{name}-{aid}:{version}"


def _default_tag(
    agent_config: Path,
    pyproject: Path | None = None,
    *,
    agent_version: str | None = None,
    agent_author: str | None = None,
) -> str:
    """Derive a default image tag as ``{agent_name}-{agent_id}:{agent_version}``.

    Uses :func:`~nemo_agents_plugin.container.metadata.extract_agent_metadata`
    to resolve the name, version, and content-addressable ID.  Kept as a
    thin wrapper around :func:`_default_tag_from_meta` so callers that
    don't already have a metadata dict (notably the unit tests) still
    have a single-argument entry point.
    """
    from nemo_agents_plugin.container.metadata import extract_agent_metadata

    meta = extract_agent_metadata(
        agent_config,
        pyproject,
        agent_version=agent_version,
        agent_author=agent_author,
    )
    return _default_tag_from_meta(meta)
