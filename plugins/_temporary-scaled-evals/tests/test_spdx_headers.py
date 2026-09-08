# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Every source file this plugin ships must declare its license."""

from __future__ import annotations

import subprocess
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent

# Extensions whose files carry the header. Everything else in the tree is either
# data (.jsonl, .json), prose (.md), or a Dockerfile, none of which a license
# scanner reads a header out of.
HEADERED_SUFFIXES = frozenset({".py", ".sql", ".sh", ".yaml", ".yml", ".toml"})

IDENTIFIER = "SPDX-License-Identifier: Apache-2.0"
COPYRIGHT = "SPDX-FileCopyrightText:"


def test_every_source_file_declares_its_license() -> None:
    """A missing header is a distribution blocker, so fail with the exact list.

    Scoped to git-tracked files: an untracked scratch file or a stale build
    artifact is not something we ship, and failing on those would make the test
    depend on whatever is lying around in a working tree.
    """
    tracked = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=PLUGIN_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    candidates = [PLUGIN_ROOT / name for name in tracked.split("\0") if name and Path(name).suffix in HEADERED_SUFFIXES]
    assert candidates, "git ls-files matched nothing; the scope filter is wrong"

    missing = []
    for path in candidates:
        # A shebang occupies line 1, so allow the header to start on line 2.
        head = "".join(path.read_text(encoding="utf-8").splitlines(keepends=True)[:4])
        if IDENTIFIER not in head or COPYRIGHT not in head:
            missing.append(str(path.relative_to(PLUGIN_ROOT)))

    assert not missing, "missing SPDX header:\n" + "\n".join(f"  {p}" for p in sorted(missing))


def test_a_shebang_still_owns_line_one() -> None:
    """Inserting a header above ``#!`` silently stops the kernel honouring it.

    The scripts stay executable-looking either way, so nothing but this notices.
    """
    tracked = subprocess.run(
        ["git", "ls-files", "-z", "*.sh"],
        cwd=PLUGIN_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    scripts = [PLUGIN_ROOT / name for name in tracked.split("\0") if name]
    assert scripts, "no shell scripts found; the glob is wrong"

    for path in scripts:
        first = path.read_text(encoding="utf-8").splitlines()[0]
        assert first.startswith("#!"), f"{path.relative_to(PLUGIN_ROOT)} starts with {first!r}"
