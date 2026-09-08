# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Directory transfer built from the single-file and exec primitives every backend already has.

No layer below the broker has a directory operation: :class:`sandboxed_gym.sandbox_types.
SandboxProvider` -- which mirrors NeMo-Gym's own provider contract -- exposes ``upload_file`` and
``download_file`` and nothing else, and there is no listing call anywhere, so ``download_dir``
cannot even enumerate what it should fetch without running a command inside the episode.
Directory transfer therefore has to be synthesized. It is synthesized *here*, once, rather than in
each client: paths are quoted in one place, the archive format is fixed by the wire contract, and
Customizer inherits the behaviour when it moves onto this package.

Backends that have a native directory transport should implement ``upload_dir``/``download_dir``
themselves and skip these helpers entirely -- OpenShell's tar-over-SSH file path is the case in
view (see the sandboxed-GRPO RFC §4.6). These helpers are the fallback, not the contract.

The archive is a gzipped tar so mode bits, symlinks and empty directories survive the round trip.
A staged workspace whose scripts lose their execute bit fails when something runs them, far from
the upload that dropped it.
"""

from __future__ import annotations

import shlex
import uuid
from typing import Protocol

from sandboxed_gym.backends.base import DirectoryTransferError
from sandboxed_gym.sandbox_types import SandboxExecResult

#: Where staged archives land inside the episode. ``/tmp`` is the one path an OCI image can be
#: relied on to have writable; the random suffix keeps concurrent transfers to one episode apart.
_STAGING_DIR = "/tmp"


class _ArchiveCapableBackend(Protocol):
    """The three primitives these helpers are written against."""

    async def exec(
        self,
        backend_id: str,
        command: str,
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_s: float | None = None,
        user: str | int | None = None,
    ) -> SandboxExecResult: ...

    async def upload_file(self, backend_id: str, path: str, content: bytes) -> None: ...

    async def download_file(self, backend_id: str, path: str) -> bytes: ...


def _staging_path() -> str:
    return f"{_STAGING_DIR}/.sandboxed-gym-{uuid.uuid4().hex}.tar.gz"


def _require_ok(result: SandboxExecResult, *, operation: str, path: str) -> None:
    """Turn a non-zero command into an error naming the operation, not just the exit code.

    ``tar`` and ``mkdir`` failures are the expected way these transfers break -- a missing
    ``tar`` binary in a minimal image, a read-only target, a path the sandbox user cannot write.
    Reported here so the caller sees which step failed rather than an opaque 500.
    """
    if result.return_code == 0:
        return
    detail = (result.stderr or result.stdout or "").strip()
    raise DirectoryTransferError(
        f"{operation} failed for {path!r} (exit {result.return_code})"
        + (f": {detail}" if detail else "")
        + ". The episode image needs `tar` and a writable /tmp for directory transfer."
    )


async def upload_dir_via_archive(
    backend: _ArchiveCapableBackend,
    backend_id: str,
    path: str,
    archive: bytes,
    *,
    timeout_s: float | None = None,
) -> None:
    """Unpack ``archive`` into ``path``, creating it if absent.

    Staged to a temporary file and removed afterwards even when the extract fails, so a failed
    transfer does not leave the archive behind inside the episode.
    """
    staged = _staging_path()
    await backend.upload_file(backend_id, staged, archive)
    quoted_path, quoted_staged = shlex.quote(path), shlex.quote(staged)
    try:
        result = await backend.exec(
            backend_id,
            f"mkdir -p {quoted_path} && tar -xzf {quoted_staged} -C {quoted_path}",
            timeout_s=timeout_s,
        )
        _require_ok(result, operation="directory upload", path=path)
    finally:
        await backend.exec(backend_id, f"rm -f {quoted_staged}", timeout_s=timeout_s)


async def download_dir_via_archive(
    backend: _ArchiveCapableBackend,
    backend_id: str,
    path: str,
    *,
    timeout_s: float | None = None,
) -> bytes:
    """Return ``path``'s contents as a gzipped tar.

    Members are relative to ``path`` (``tar -C path .``), so unpacking into a different directory
    on the far side does not nest the tree under its original name.
    """
    staged = _staging_path()
    quoted_path, quoted_staged = shlex.quote(path), shlex.quote(staged)
    try:
        result = await backend.exec(
            backend_id,
            f"tar -czf {quoted_staged} -C {quoted_path} .",
            timeout_s=timeout_s,
        )
        _require_ok(result, operation="directory download", path=path)
        return await backend.download_file(backend_id, staged)
    finally:
        await backend.exec(backend_id, f"rm -f {quoted_staged}", timeout_s=timeout_s)
