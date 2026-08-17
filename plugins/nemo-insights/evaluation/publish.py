# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Mint the next state ref and upload a candidate bundle to CSS S3.

``uv run python -m evaluation publish FILE --reason "why"`` works from a
maintainer machine with the CSS credentials loaded from ``evaluation/.env``.
"""

import getpass
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

from evaluation import artifact, release


def read_manifest(bundle: Path) -> dict:
    """Read the bundle's ``state/manifest.json`` without fully extracting it."""
    if not bundle.is_file():
        sys.exit(f"no such bundle file: {bundle}")
    proc = subprocess.run(
        ["tar", "--zstd", "-xOf", str(bundle), "state/manifest.json"],
        capture_output=True,
        text=True,
    )
    try:
        manifest = json.loads(proc.stdout) if proc.returncode == 0 else None
    except json.JSONDecodeError:
        manifest = None
    if not isinstance(manifest, dict) or not artifact.is_export_manifest(manifest):
        sys.exit(f"publish: {bundle.name} is not an evaluation export bundle — only export bundles are published")
    return manifest


def _sanitize_reason(reason: str) -> str:
    """Collapse a reason into one S3 metadata value."""
    return re.sub(r"\s+", " ", reason).strip()


def publish(candidate: Path, *, reason: str | None, env: Mapping[str, str] | None = None) -> str:
    """Mint the next ref and upload the bundle to CSS S3.

    ``reason=None`` falls back to ``REASON`` and then the candidate manifest.
    The reason, publisher, and SHA-256 digest are stored as S3 object metadata.
    """
    env = os.environ if env is None else env
    manifest = read_manifest(candidate)
    if reason is None:
        reason = env.get("REASON") or str(manifest.get("reason") or "")
    ref = release.next_ref(release.latest_ref(release.object_names()))
    tarball = candidate.parent / f"{ref}.tar.zst"
    shutil.copy2(candidate, tarball)
    release.upload_ref(
        ref,
        tarball,
        metadata={
            "reason": _sanitize_reason(reason),
            "published-by": getpass.getuser(),
            "sha256": hashlib.sha256(tarball.read_bytes()).hexdigest(),
        },
    )
    print(f"published {ref}")
    return ref
