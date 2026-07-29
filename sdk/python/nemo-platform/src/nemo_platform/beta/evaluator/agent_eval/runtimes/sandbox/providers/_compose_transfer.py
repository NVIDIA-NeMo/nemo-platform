# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# ruff: noqa: I001 - the vendored SDK mirror uses different import-order settings.

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

_FILE_PARENT_CREATED = "__NEMO_COMPOSE_FILE_PARENT_CREATED__"
_FILE_PARENT_EXISTING = "__NEMO_COMPOSE_FILE_PARENT_EXISTING__"
_FILE_PARENT_OPERATION = "nemo-compose-file-parent"
_PREPARE_FILE_PARENT_SCRIPT = """\
parent=$1
identity=$2
ancestor=${parent%/*}
[ -n "$ancestor" ] || ancestor=/
mkdir -p -- "$ancestor" || exit 1
cursor=$ancestor
while [ "$cursor" != / ]; do
    [ -d "$cursor" ] && [ ! -L "$cursor" ] || exit 1
    cursor=${cursor%/*}
    [ -n "$cursor" ] || cursor=/
done
if mkdir -- "$parent" 2>/dev/null; then
    [ -d "$parent" ] && [ ! -L "$parent" ] || exit 1
    chown -h "$identity" -- "$parent" || exit 1
    [ -d "$parent" ] && [ ! -L "$parent" ] || exit 1
    printf '%s' '__NEMO_COMPOSE_FILE_PARENT_CREATED__'
elif [ -d "$parent" ] && [ ! -L "$parent" ]; then
    printf '%s' '__NEMO_COMPOSE_FILE_PARENT_EXISTING__'
else
    exit 1
fi
"""


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


async def _prepare_file_parent(
    cli: _ComposeCli,
    session: _ComposeSession,
    parent: str,
    identity: str,
    *,
    command_timeout_seconds: float,
) -> None:
    """Atomically classify a file parent and repair only a directory this operation creates.

    The target shell receives all dynamic values as positional arguments. Its exact
    sentinel is accepted only after the complete create/classify operation succeeds.

    Args:
        cli: Command gateway bound to the active Compose lifecycle.
        session: Active lifecycle identifying the target service and environment.
        parent: Normalized absolute parent path for the uploaded file.
        identity: Numeric target-service ``UID:GID``.
        command_timeout_seconds: Deadline for the privileged operation.

    Raises:
        RuntimeError: If the operation fails, times out, or emits unexpected output.
    """
    result = await _run_target_root(
        cli,
        session,
        [
            "sh",
            "-c",
            _PREPARE_FILE_PARENT_SCRIPT,
            _FILE_PARENT_OPERATION,
            parent,
            identity,
        ],
        command_timeout_seconds=command_timeout_seconds,
    )
    if not result.ok or result.stderr or result.stdout not in {_FILE_PARENT_CREATED, _FILE_PARENT_EXISTING}:
        raise RuntimeError(
            cli.failure_message(
                "Compose upload target preparation failed",
                result,
                session.environment,
            )
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
        if directory:
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
        else:
            if session.target_identity is None:
                session.target_identity = await _target_identity(
                    cli,
                    session,
                    command_timeout_seconds=command_timeout_seconds,
                )
            await _prepare_file_parent(
                cli,
                session,
                remote_directory,
                session.target_identity,
                command_timeout_seconds=command_timeout_seconds,
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
    ownership_command = ["chown", "-R", session.target_identity, "--", container_target]
    if not directory:
        ownership_command = ["chown", session.target_identity, "--", container_target]
    ownership = await _run_target_root(
        cli,
        session,
        ownership_command,
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
            "-c",
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
