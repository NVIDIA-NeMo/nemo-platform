# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Download + safely expand an uploaded NAT project bundle stored as a platform fileset.

An uploaded project is stored as a single-file fileset (one zip). The inspect endpoint, manifest
creation, and the war-game job all need the project on local disk, so this module downloads the whole
fileset and expands the zip with hardening (no absolute members, no symlinks, no traversal, bounded
size/entry count) — the archive is untrusted user input and is never executed here (only statically
scanned by ``iron-swarm inspect`` and later run inside the OpenShell sandbox).
"""

from __future__ import annotations

import stat
import zipfile
from pathlib import Path

import fsspec.asyn
from nemo_platform import NeMoPlatform
from nemo_platform.filesets import FilesetFileSystem
from nemo_platform_plugin.client.adapter import client_from_platform
from nemo_platform_plugin.files.client import FilesClient

_MAX_ENTRIES = 10_000
_MAX_UNCOMPRESSED_BYTES = 500 * 1024 * 1024  # 500 MB expanded — a NAT project, not a dataset.
_IGNORED_TOP_LEVEL = frozenset({"__MACOSX"})


def _is_absolute_member(name: str) -> bool:
    """Return whether a zip member name is an absolute path (POSIX, Windows, or drive-letter)."""
    return name.startswith(("/", "\\")) or (len(name) >= 2 and name[1] == ":")


def download_fileset(sdk: NeMoPlatform, ref: str, dest: Path) -> Path:
    """Download an entire fileset (all files) into *dest* using the sync platform SDK.

    Whole-fileset download only — Iron Swarm stores the project as one zip, so there is no
    fragment/glob handling (unlike the evaluator's dataset downloader).
    """
    fs = FilesetFileSystem(client=client_from_platform(sdk, FilesClient))
    dest.mkdir(parents=True, exist_ok=True)
    source = ref.rstrip("/") + "/"
    fsspec.asyn.sync(fs.loop, fs._get, source, str(dest), True)
    return dest


def upload_file_to_fileset(sdk: NeMoPlatform, local_path: Path, *, workspace: str) -> str:
    """Upload a single file into a freshly-created fileset and return its ``workspace/name`` ref.

    Used to persist a war-game's produced garak hitlog so a later run can replay it: platform
    persistent job storage is per-job, so the hitlog must live in a fileset to survive across runs.
    """
    fileset = sdk.files.upload(
        local_path=str(local_path),
        workspace=workspace,
        fileset_auto_create=True,  # generates a unique fileset name
    )
    return f"{workspace}/{fileset.name}"


def extract_zip_safely(zip_path: Path, dest: Path) -> Path:
    """Expand *zip_path* into *dest*, rejecting absolute/symlink/traversing members and oversized archives.

    The size cap sums ``ZipInfo.file_size``, which is the archive's own declared figure. That is a sound
    bound because ``zipfile`` also *reads* against it: a member claiming to be smaller than its data is
    truncated at the declared length and fails its CRC, so an under-reporting bomb cannot expand past
    the cap — it errors out instead.
    """
    dest.mkdir(parents=True, exist_ok=True)
    dest_resolved = dest.resolve()
    with zipfile.ZipFile(zip_path) as archive:
        infos = archive.infolist()
        if len(infos) > _MAX_ENTRIES:
            raise ValueError(f"Project archive has too many entries ({len(infos)} > {_MAX_ENTRIES}).")
        total = 0
        for info in infos:
            name = info.filename
            if _is_absolute_member(name):
                raise ValueError(f"Archive member has an absolute path: {name!r}")
            if stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError(f"Archive contains a symlink ({name!r}); not allowed.")
            if not (dest / name).resolve().is_relative_to(dest_resolved):
                raise ValueError(f"Archive member escapes the destination: {name!r}")
            total += info.file_size
            if total > _MAX_UNCOMPRESSED_BYTES:
                raise ValueError("Project archive is too large when uncompressed (max 500 MB).")
        archive.extractall(dest)
    return dest


def download_and_extract_project(sdk: NeMoPlatform, ref: str, workdir: Path) -> Path:
    """Download the project fileset into *workdir*, expand its zip, and return the project root.

    Collapses a single wrapping top-level directory (the common ``repo-name/…`` zip layout) so the
    returned path is the installable project itself.
    """
    bundle_dir = download_fileset(sdk, ref, workdir / "bundle")
    zips = sorted(bundle_dir.rglob("*.zip"))
    if not zips:
        raise ValueError(f"Fileset {ref!r} contains no .zip project bundle.")
    extracted = extract_zip_safely(zips[0], workdir / "project")
    entries = [p for p in extracted.iterdir() if p.name not in _IGNORED_TOP_LEVEL]
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    return extracted
