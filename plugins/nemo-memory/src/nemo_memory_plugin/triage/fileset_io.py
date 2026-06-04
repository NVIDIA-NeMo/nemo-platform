# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared helpers for resolving a path-or-fileset reference to a local file.

Used by all three memory NemoJobs (``triage`` / ``eval`` / ``export``).

The input-resolution dispatch heuristic: leading ``.``, ``/``, ``..``,
or ``~`` and any string that already exists on disk are paths;
everything else falls through to fileset resolution. We deliberately
keep the local-exists check (unlike the RFC LJ-3 canonical helper used
for *output* targets) because input files are real things on disk and
the UX win of "just point at the file" outweighs the small risk of a
bare name colliding with a local file accidentally.

For fileset inputs, the underlying ``fileset_path`` context manager is
vendored locally (rather than imported from
``nemo_agents_plugin.usage.sources.fileset``) so this plugin has no
cross-plugin dependency on nemo-agents. The vendored helper is a small,
self-contained ~25 lines; the cost of duplication is less than the cost
of a hard install-time dependency that would defeat the optional-install
property this plugin extraction was designed to deliver.
"""

from __future__ import annotations

import contextlib
import logging
import tempfile
from collections.abc import Iterator
from pathlib import Path

from nemo_platform import NeMoPlatform
from nemo_platform_plugin.job_context import JobContext
from nemo_platform_plugin.refs import (
    FilesetRef,
    LocalDir,
    OutputTarget,
    classify_output_target,
)

logger = logging.getLogger(__name__)


class FilesetRefError(ValueError):
    """Raised when a fileset reference is malformed (e.g., multi-segment)."""


class FilesetDownloadError(RuntimeError):
    """Raised when the SDK fails to download a fileset (network, auth, missing)."""


@contextlib.contextmanager
def _fileset_path(
    ref: FilesetRef,
    *,
    sdk: NeMoPlatform,
    workspace: str,
) -> Iterator[Path]:
    """Download *ref* to a tempdir and yield the path.

    Vendored from ``nemo_agents_plugin.usage.sources.fileset`` so the
    memory plugin has no install-time dependency on nemo-agents. The
    accepted shapes are ``name`` (uses *workspace*) or
    ``workspace/name``. Multi-segment refs (``a/b/c``) are rejected
    here rather than letting the slash leak into the tempdir prefix
    where :func:`tempfile.mkdtemp` raises a confusing error.
    """
    raw = str(ref)
    if "/" in raw:
        ws, name = raw.split("/", 1)
    else:
        ws, name = workspace, raw

    if "/" in name:
        raise FilesetRefError(
            f"invalid fileset reference {raw!r}: name segment must not contain '/' "
            f"(use 'workspace/name' for a workspace-qualified reference)"
        )
    if name in {"", ".", ".."}:
        raise FilesetRefError(
            f"invalid fileset reference {raw!r}: name segment must be a real fileset name "
            f"(empty / '.' / '..' are rejected)"
        )
    if not ws:
        raise FilesetRefError(
            f"invalid fileset reference {raw!r}: workspace must be non-empty "
            f"(set workspace on the spec, or use 'workspace/name' form)"
        )

    with tempfile.TemporaryDirectory(prefix=f".memory-fileset-{name}-") as tmp:
        tmp_path = Path(tmp)
        logger.debug("downloading fileset %s/%s to %s", ws, name, tmp_path)
        try:
            sdk.files.download(
                remote_path="",
                local_path=str(tmp_path),
                fileset=name,
                workspace=ws,
            )
        except (FilesetRefError, FilesetDownloadError):
            raise
        except Exception as exc:
            raise FilesetDownloadError(f"failed to download fileset {ws}/{name}: {exc}") from exc
        yield tmp_path


def looks_pathy(ref: str) -> bool:
    """True when *ref* looks like a filesystem path rather than a fileset reference.

    Leading ``.``, ``/``, or ``~`` are unambiguous path shapes; any
    string that exists locally is also a path. A bare name that does
    not exist locally falls through to fileset resolution.
    """
    if ref.startswith(("/", "./", "../", "~")):
        return True
    try:
        return Path(ref).expanduser().exists()
    except OSError:
        # Path() can raise on pathologically long inputs; treat as non-path.
        return False


@contextlib.contextmanager
def resolve_input_artifact(
    ref: str,
    *,
    workspace: str,
    sdk: NeMoPlatform | None,
    suffix: str,
    kind_label: str,
) -> Iterator[Path]:
    """Yield a local :class:`Path` to an input artifact (corpus or report).

    *ref* is either a local path (yielded directly) or a fileset reference.
    For fileset refs, the fileset is downloaded to a tempdir and the single
    file with the given *suffix* (e.g. ``".md"`` for a corpus, ``".json"``
    for a triage artifact) is yielded. Zero or multiple matches raise so
    the caller doesn't silently pick the wrong file.

    *kind_label* is a short human-readable name ("corpus", "baseline
    artifact", "candidate artifact") used in error messages so a failed
    lookup tells the user exactly which input was bad. Without it the
    error would just say "fileset X has no .json file" and you'd have
    to dig into the call site to know whether X was the baseline or the
    candidate.

    Failures are wrapped as :class:`RuntimeError` so the caller can
    surface one consistent error type to job runners regardless of
    whether the artifact came from disk or the platform.
    """
    if looks_pathy(ref):
        path = Path(ref).expanduser().resolve()
        if not path.exists():
            raise RuntimeError(
                f"{kind_label} path does not exist: {path}. Set the reference to a "
                "valid local file or to a NeMo Platform fileset reference (workspace/name)."
            )
        yield path
        return

    # Fileset reference. The staging helper is vendored above so no
    # cross-plugin import is needed.
    try:
        fref = FilesetRef(ref)
    except Exception as err:
        raise RuntimeError(
            f"Could not parse {kind_label} reference {ref!r} as a fileset reference. "
            "Use 'fileset-name' (with the workspace field set) or 'workspace/fileset-name'."
        ) from err

    if sdk is None:
        raise RuntimeError(
            f"Resolving {kind_label} from fileset {ref!r} requires a 'sdk: NeMoPlatform', "
            "but no platform SDK was available. Set NMP_BASE_URL (so the local CLI can "
            "build a default SDK), pass an explicit sdk via NemoJobScheduler.run_local(sdk=...), "
            f"or use a local path for {kind_label} instead."
        )

    try:
        with _fileset_path(fref, sdk=sdk, workspace=workspace) as tmp:
            matches = sorted(tmp.rglob(f"*{suffix}"))
            if not matches:
                raise RuntimeError(
                    f"Fileset {ref!r} (workspace={workspace!r}) contains no {suffix} files. "
                    f"Expected a single {suffix} file for the {kind_label}."
                )
            if len(matches) > 1:
                names = [p.name for p in matches]
                raise RuntimeError(
                    f"Fileset {ref!r} contains multiple {suffix} files: {names}. "
                    f"Expected exactly one {suffix} file for the {kind_label}; "
                    "create separate filesets per artifact or remove the extras."
                )
            yield matches[0]
    except (FilesetRefError, FilesetDownloadError) as err:
        raise RuntimeError(f"Failed to stage {kind_label} fileset {ref!r}: {err}") from err


@contextlib.contextmanager
def resolve_output_target(
    output: OutputTarget | None,
    *,
    workspace: str,
    basename: str,
    ctx: JobContext,
    sdk: NeMoPlatform | None,
    persistent_subdir: str,
    job_label: str,
    expected_suffixes: tuple[str, ...] = (".json", ".md"),
) -> Iterator[Path]:
    """Yield the local directory artifacts should be written to.

    Shared output-resolution helper for triage and eval
    (and any future NemoJob in this subpackage that produces a
    ``{basename}.json`` + ``{basename}.md`` artifact pair).

    Branches on the output union shape:

    - ``None`` → ``ctx.storage.persistent / persistent_subdir``. Survives
      across job runs in the platform-injected persistent volume.
    - :class:`LocalDir` → that directory, ``mkdir -p``-ed.
    - :class:`FilesetRef` → a tempdir under ``ctx.storage.ephemeral``. On
      successful exit, every ``{basename}{suffix}`` in *expected_suffixes*
      is uploaded to the named fileset (auto-created if missing) via
      ``sdk.files.upload``, then the tempdir is removed. A failed run
      (any exception out of the ``with`` body) skips the upload so the
      fileset never holds a half-finished pair.

    *job_label* is a short string ("triage", "memory-eval") used
    in log lines and error messages so a reviewer scanning multi-job
    output can tell which job emitted which line. *persistent_subdir*
    keeps the two jobs' default outputs from colliding in the same
    persistent volume.

    *sdk* is required only on the fileset branch; checked up front so a
    long job doesn't run for ten minutes only to discover it can't
    deliver the artifacts.
    """
    if output is None:
        local = ctx.storage.persistent / persistent_subdir
        local.mkdir(parents=True, exist_ok=True)
        logger.info("%s: writing artifacts to platform-persistent dir %s", job_label, local)
        yield local
        return

    cls = classify_output_target(str(output))
    if cls is LocalDir:
        local = Path(str(output)).expanduser().resolve()
        local.mkdir(parents=True, exist_ok=True)
        logger.info("%s: writing artifacts to local dir %s", job_label, local)
        yield local
        return

    if sdk is None:
        raise RuntimeError(
            f"{job_label} requires a 'sdk: NeMoPlatform' to upload artifacts to fileset "
            f"{output!r}, but no platform SDK was available. Set NMP_BASE_URL (so the "
            "local CLI can build a default SDK), pass an explicit sdk via "
            "NemoJobScheduler.run_local(sdk=...), or use a local path for 'output' instead."
        )

    ref = FilesetRef(str(output))
    if "/" in ref:
        ws, name = ref.split("/", 1)
    else:
        ws, name = workspace, str(ref)

    with tempfile.TemporaryDirectory(
        prefix=f".{job_label}-output-{name}-",
        dir=str(ctx.storage.ephemeral),
    ) as tmp:
        tmp_path = Path(tmp)
        logger.info(
            "%s: staging artifacts in %s; will upload to fileset %s/%s on success.",
            job_label,
            tmp_path,
            ws,
            name,
        )
        should_upload = True
        try:
            yield tmp_path
        except BaseException:
            # Don't pollute the fileset with broken / partial outputs from a
            # crashed run. Re-raise so the job-runner sees the original error.
            should_upload = False
            raise
        finally:
            if should_upload:
                for suffix in expected_suffixes:
                    artifact = tmp_path / f"{basename}{suffix}"
                    if not artifact.exists():
                        raise RuntimeError(
                            f"{job_label}: expected artifact {artifact} was not "
                            "produced. The fileset upload was aborted to avoid a partial pair."
                        )
                    sdk.files.upload(
                        local_path=str(artifact),
                        fileset=name,
                        workspace=ws,
                        fileset_auto_create=True,
                    )
                    logger.info(
                        "%s: uploaded %s to fileset %s/%s.",
                        job_label,
                        artifact.name,
                        ws,
                        name,
                    )
