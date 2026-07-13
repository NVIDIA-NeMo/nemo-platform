# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The content digest — a stable fingerprint of a dataset's file listing."""

from __future__ import annotations

import hashlib

from nemo_datasets_plugin.profiler.file_source import FileEntry


def content_digest(entries: list[FileEntry]) -> str:
    """A stable digest over the (path, size, checksum) of every file, sorted by path.

    Uses only listing metadata — no file reads — so it is cheap and a profile can self-describe the
    inputs it was built from; a mismatch on re-listing means the profile is stale. When a source
    reports no checksum, (path, size) is the fallback, which cannot detect a same-size in-place edit.
    """
    hasher = hashlib.sha256()
    for entry in sorted(entries, key=lambda entry: entry.path):
        hasher.update(entry.path.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(str(entry.size_bytes).encode("utf-8"))
        hasher.update(b"\0")
        hasher.update((entry.checksum or "").encode("utf-8"))
        hasher.update(b"\n")
    return f"sha256:{hasher.hexdigest()}"
