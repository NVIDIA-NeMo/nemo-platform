# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path

from data_designer_nemo.filesystem import make_filesystem
from filesets import FilesetPathError, build_fileset_ref, parse_fileset_ref
from nemo_platform import NeMoPlatform

_HF_PREFIX = "hf://"


def materialize_corpus(
    corpus: str,
    *,
    dest: Path,
    sdk: NeMoPlatform,
    workspace: str,
    hf_token: str | None = None,
) -> Path:
    """Download a fileset or HuggingFace corpus (or use a local path) to ``dest``."""
    if corpus.startswith(_HF_PREFIX):
        return _download_hf(corpus, dest, token=hf_token)

    local = Path(corpus)
    if local.exists():
        return local.resolve()

    return _download_fileset(corpus, dest=dest, sdk=sdk, workspace=workspace)


def _download_hf(corpus: str, dest: Path, *, token: str | None) -> Path:
    from huggingface_hub import snapshot_download

    rest = corpus[len(_HF_PREFIX) :]
    parts = rest.split("/", 2)
    if len(parts) < 2:
        raise ValueError(f"Invalid hf:// URI: {corpus}. Expected hf://org/dataset[@revision][/subdir]")

    repo_id = f"{parts[0]}/{parts[1]}"
    revision = None
    if "@" in parts[1]:
        dataset_name, revision = parts[1].rsplit("@", 1)
        repo_id = f"{parts[0]}/{dataset_name}"
    subdir = parts[2] if len(parts) > 2 else None

    local_dir = Path(
        snapshot_download(
            repo_id=repo_id,
            repo_type="dataset",
            local_dir=str(dest),
            revision=revision,
            allow_patterns=f"{subdir}/**" if subdir else None,
            token=token,
        )
    )
    return local_dir / subdir if subdir else local_dir


def _download_fileset(corpus: str, *, dest: Path, sdk: NeMoPlatform, workspace: str) -> Path:
    try:
        fileset_workspace, fileset, fragment = parse_fileset_ref(corpus, workspace_fallback=workspace)
    except FilesetPathError as exc:
        raise ValueError(f"Invalid corpus reference {corpus!r}: {exc}") from exc

    root = build_fileset_ref(fragment, workspace=fileset_workspace, fileset=fileset)
    dest.mkdir(parents=True, exist_ok=True)
    fs = make_filesystem(sdk)
    fs.get(root, str(dest), recursive=True)
    return dest
