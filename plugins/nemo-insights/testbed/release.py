# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""State-version release ops shared by the CLI and the CI publish step.

Reference resolution + download operations for the testbed-insights workflow.
Bundles live as assets named state-v<N>.tar.zst on the `testbed-state` release.
"""

import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

RELEASE_TAG = "testbed-state"
_ASSET = re.compile(r"^state-v(\d+)\.tar\.zst$")


def latest_ref(names: list[str]) -> str | None:
    """Find the latest state version from a list of asset names."""
    versions = [int(m.group(1)) for n in names if (m := _ASSET.match(n))]
    return f"state-v{max(versions)}" if versions else None


def next_ref(latest: str | None) -> str:
    """Generate the next state version ref after the given latest."""
    return f"state-v{int(latest.removeprefix('state-v')) + 1}" if latest else "state-v1"


def lock_ref(lock_path: Path, subject: str) -> str | None:
    """The subject's pinned state ref from the lock file's ``[subjects]`` table.

    Returns None when the file is missing or the subject has no entry. A lock
    file without a ``[subjects]`` table (e.g. the retired single-pin
    ``state_ref = "..."`` format) exits with a migration message — states are
    per-produce-dispatch compositions now, so one global pin cannot be right
    for every subject.
    """
    if not lock_path.exists():
        return None
    subjects = tomllib.loads(lock_path.read_text(encoding="utf-8")).get("subjects")
    if not isinstance(subjects, dict):
        sys.exit(
            f"{lock_path} has no [subjects] table — migrate the old single-pin format "
            "to per-subject pins:\n\n"
            "[subjects]\n"
            'tau2-airline = "state-v6"'
        )
    value = subjects.get(subject)
    return None if value is None else str(value)


def _gh(*args: str) -> str:
    """Run a gh CLI command and return stdout; surface stderr on failure.

    A missing gh binary is a clean SystemExit with an install pointer (doctor
    flags it too), not a raw FileNotFoundError traceback.
    """
    try:
        return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout
    except FileNotFoundError:
        sys.exit("gh CLI not found — install GitHub CLI (https://cli.github.com) and run `gh auth login`")
    except subprocess.CalledProcessError as e:
        print(e.stderr, file=sys.stderr, end="")
        raise


def _release_asset_names() -> list[str]:
    """Fetch the list of asset names from the testbed-state release.

    Returns an empty list if the release does not exist (404).
    Raises on other failures (outages, auth errors, etc.).
    """
    try:
        out = _gh("release", "view", RELEASE_TAG, "--json", "assets")
    except subprocess.CalledProcessError as e:
        if "not found" in (e.stderr or "").lower():
            return []
        raise
    return [a["name"] for a in json.loads(out).get("assets", [])]


def resolve_state(state: str | None, *, subject: str | None, lock_path: Path) -> str:
    """Resolve the state ref to restore: an explicit ref verbatim, else the subject's lock pin.

    An explicit *state* must be a published ref (``state-v<N>``) — local bundle
    files are the caller's business (the CLI detects existing paths before this
    is reached), so anything else here is a typo and exits naming the pattern.
    ``state=None`` reads the subject's pin from *lock_path*'s ``[subjects]``
    table; a missing entry/file (or a subject-less caller, e.g. restore) is a
    hard SystemExit, so nothing silently analyzes a state nobody pinned.
    """
    if state is not None:
        if not re.fullmatch(r"state-v\d+", state):
            sys.exit(
                f"invalid state ref '{state}' — expected state-v<N> (e.g. state-v6); a local bundle "
                "file goes through --state FILE on analyze, or the positional FILE on restore"
            )
        return state
    if subject is not None and (pinned := lock_ref(lock_path, subject)):
        if not re.fullmatch(r"state-v\d+", pinned):
            # A typo'd pin must die naming the entry, not flow into a doomed gh download.
            sys.exit(f"state.lock entry for '{subject}' is '{pinned}' — expected state-v<N> (e.g. state-v6)")
        return pinned
    # This serves both analyze and restore, so the guidance names each command's
    # real surface instead of recommending flags one of them lacks.
    sys.exit(
        f"no state.lock entry for subject '{subject}' — add it under [subjects] "
        "after minting a fixture, or pass an explicit state "
        "(analyze: --live / --state <state-vN|FILE>; restore: FILE / --state state-vN)"
    )


def download_ref(ref: str, dest_dir: Path) -> Path:
    """Download a state version tarball from the testbed-state release.

    Returns the path to the tarball. Published refs are immutable, so an
    already-downloaded ``<ref>.tar.zst`` in *dest_dir* is reused without
    invoking gh (one printed line says so). On a fresh download, ``--clobber``
    overwrites any leftover file from a prior run (gh refuses to overwrite by
    default, which would make re-downloading the same ref crash). Failures
    surface gh stderr and propagate the exception.
    """
    dest = dest_dir / f"{ref}.tar.zst"
    if dest.is_file():
        print(f"using cached {ref}.tar.zst")
        return dest
    dest_dir.mkdir(parents=True, exist_ok=True)
    _gh("release", "download", RELEASE_TAG, "--pattern", f"{ref}.tar.zst", "--dir", str(dest_dir), "--clobber")
    return dest
