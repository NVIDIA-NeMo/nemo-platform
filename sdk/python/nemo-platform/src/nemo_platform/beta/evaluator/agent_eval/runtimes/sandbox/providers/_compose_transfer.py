# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""File-transfer preparation and ownership repair for Compose sandboxes."""

from __future__ import annotations

import os
import posixpath
import re
from collections.abc import Sequence
from pathlib import Path

from ..base import SandboxCreateError
from ._compose_cli import _ComposeCli
from ._compose_contracts import ComposeCommandResult
from ._compose_state import _ComposeSession


async def _run_target_root(
    cli: _ComposeCli,
    session: _ComposeSession,
    command: Sequence[str],
    *,
    command_timeout_seconds: float,
) -> ComposeCommandResult:
    """Run a command as root in the configured target service.

    Args:
        cli: Command gateway bound to the active Compose lifecycle.
        session: Active lifecycle identifying the target service and environment.
        command: Executable and arguments to append after the target service name.
        command_timeout_seconds: Deadline for the privileged command.

    Returns:
        Captured result for the privileged Compose exec command.
    """
    return await cli.run_compose(
        ["exec", "--no-TTY", "--user", "0", session.target_service, *command],
        environment=session.environment,
        timeout=command_timeout_seconds,
    )


async def _copy_to_service(
    cli: _ComposeCli,
    session: _ComposeSession,
    source: Path,
    target: str,
    *,
    directory: bool,
    command_timeout_seconds: float,
) -> None:
    """Copy a host path into the target service and repair ownership.

    Args:
        cli: Command gateway bound to the active Compose lifecycle.
        session: Active lifecycle identifying the target service and environment.
        source: Host file or directory to copy.
        target: Destination path inside the target service.
        directory: When ``True``, create the full target and copy only ``source`` contents;
            otherwise create only the file's parent and copy the file itself.
        command_timeout_seconds: Deadline for each Compose operation.

    Raises:
        RuntimeError: If target preparation, copying, or ownership repair fails.
        SandboxCreateError: If the target service runtime identity cannot be determined.

    Example:
        With ``directory=True``, source ``/tmp/work`` is passed as ``/tmp/work/.`` so
        Docker merges its contents directly into the prepared target directory.
    """
    container_target = _absolute_container_path(target)
    remote_directory = container_target if directory else posixpath.dirname(container_target)
    if remote_directory != "/":
        prepared = await _run_target_root(
            cli,
            session,
            ["mkdir", "-p", "--", remote_directory],
            command_timeout_seconds=command_timeout_seconds,
        )
        if not prepared.ok:
            raise RuntimeError(
                cli.failure_message(
                    "Compose upload target preparation failed",
                    prepared,
                    session.environment,
                )
            )
    copy_source = f"{source}{os.sep}." if directory else str(source)
    result = await cli.run_compose(
        ["cp", copy_source, f"{session.target_service}:{container_target}"],
        environment=session.environment,
        timeout=command_timeout_seconds,
    )
    if not result.ok:
        raise RuntimeError(cli.failure_message("Compose upload failed", result, session.environment))
    if session.target_identity is None:
        session.target_identity = await _target_identity(
            cli,
            session,
            command_timeout_seconds=command_timeout_seconds,
        )
    ownership = await _run_target_root(
        cli,
        session,
        ["chown", "-R", session.target_identity, "--", container_target],
        command_timeout_seconds=command_timeout_seconds,
    )
    if not ownership.ok:
        raise RuntimeError(
            cli.failure_message("Compose upload ownership repair failed", ownership, session.environment)
        )


async def _copy_from_service(
    cli: _ComposeCli,
    session: _ComposeSession,
    source: str,
    target: Path,
    *,
    directory: bool,
    command_timeout_seconds: float,
) -> None:
    """Copy a target-service path to a prepared host destination.

    Args:
        cli: Command gateway bound to the active Compose lifecycle.
        session: Active lifecycle identifying the target service and environment.
        source: File or directory path inside the target service.
        target: Host destination path.
        directory: When ``True``, create the target directory and copy source contents;
            otherwise create only the target file's parent.
        command_timeout_seconds: Deadline for the Compose copy command.

    Raises:
        RuntimeError: If the Compose copy command fails.
    """
    if directory:
        target.mkdir(parents=True, exist_ok=True)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
    copy_source = posixpath.join(source, ".") if directory else source
    result = await cli.run_compose(
        ["cp", f"{session.target_service}:{copy_source}", str(target)],
        environment=session.environment,
        timeout=command_timeout_seconds,
    )
    if not result.ok:
        raise RuntimeError(cli.failure_message("Compose download failed", result, session.environment))


async def _target_identity(
    cli: _ComposeCli,
    session: _ComposeSession,
    *,
    command_timeout_seconds: float,
) -> str:
    """Read the runtime ``UID:GID`` of the target service user.

    Args:
        cli: Command gateway bound to the active Compose lifecycle.
        session: Active lifecycle identifying the target service and command environment.
        command_timeout_seconds: Deadline for the identity command.

    Returns:
        Numeric identity formatted as ``UID:GID`` for ``chown``.

    Raises:
        SandboxCreateError: If the identity command fails or emits an unexpected value.
    """
    result = await cli.run_compose(
        [
            "exec",
            "--no-TTY",
            session.target_service,
            "sh",
            "-lc",
            'printf "%s:%s" "$(id -u)" "$(id -g)"',
        ],
        environment=session.environment,
        timeout=command_timeout_seconds,
    )
    identity = result.stdout.strip()
    if not result.ok or not re.fullmatch(r"\d+:\d+", identity):
        raise SandboxCreateError(
            cli.failure_message(
                "Could not determine target service identity",
                result,
                session.environment,
            )
        )
    return identity


def _absolute_container_path(path: str) -> str:
    """Normalize a Docker container path against its root directory.

    Docker copy commands interpret relative container paths from ``/``, while commands
    executed in a container interpret them from the image or service working directory.
    Normalizing once keeps preparation, copy, and ownership repair on the same target.

    Args:
        path: Absolute or root-relative POSIX container path.

    Returns:
        Normalized absolute POSIX path.

    Raises:
        ValueError: If ``path`` is empty.

    Example:
        ``work/output.txt`` becomes ``/work/output.txt``.
    """
    if not path:
        raise ValueError("Container path cannot be empty")
    return posixpath.normpath(f"/{path.lstrip('/')}")
