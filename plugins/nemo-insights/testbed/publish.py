# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Mint the next state ref, upload a candidate bundle, and update the fixture catalog.

``uv run python -m testbed publish FILE --reason "why"`` works from a
maintainer machine with ``gh`` access to the fixture repository. The catalog's
"Minted by" column records the GitHub Actions run when
``GITHUB_RUN_ID``/``GITHUB_REPOSITORY`` are set, else ``laptop (<user>)``; the
"Contents" column comes from the bundle's own manifest (subjects +
per-collection doc counts), so the catalog can never disagree with what the
asset actually holds.
"""

import getpass
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

from testbed import release

RELEASE_TAG = release.RELEASE_TAG
CATALOG_MARKER = "<!-- fixture-catalog: newest rows are auto-inserted below by the publish step -->"


def read_manifest(bundle: Path) -> dict:
    """The bundle's ``state/manifest.json`` (tar peek, no full extract).

    Only ``kind: testbed-export`` bundles are publishable — the catalog row is
    built from the manifest, so a bundle without one has nothing honest to say
    in the Contents column. Hard exit otherwise.
    """
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
    if not isinstance(manifest, dict) or manifest.get("kind") != "testbed-export":
        sys.exit(f"publish: {bundle.name} is not a testbed-export bundle — only export bundles are published")
    return manifest


def contents_column(manifest: dict) -> str:
    """Catalog "Contents": the bundle's subjects and its per-collection doc totals."""
    subjects = ", ".join(manifest.get("subjects") or []) or "?"
    totals = {"spans": 0, "annotations": 0, "evaluator_results": 0}
    for ws_counts in (manifest.get("counts") or {}).values():
        for key in totals:
            totals[key] += int(ws_counts.get(key) or 0)
    return (
        f"{subjects} — {totals['spans']} spans, {totals['annotations']} annotations, "
        f"{totals['evaluator_results']} evaluator results"
    )


def minted_by(env: Mapping[str, str]) -> str:
    """A run link when publishing from CI, else the laptop user."""
    run_id, repo = env.get("GITHUB_RUN_ID"), env.get("GITHUB_REPOSITORY")
    if run_id and repo:
        return f"[run {run_id}](https://github.com/{repo}/actions/runs/{run_id})"
    return f"laptop ({getpass.getuser()})"


def _sanitize_reason(reason: str) -> str:
    """Force *reason* to stay one Markdown table cell.

    A raw ``|`` adds phantom columns and a newline terminates the row — GitHub
    stops rendering the release table there, hiding every older catalog row.
    Whitespace runs (newlines included) collapse to single spaces; pipes are
    escaped as ``\\|``.
    """
    return re.sub(r"\s+", " ", reason).strip().replace("|", "\\|")


def catalog_row(ref: str, manifest: dict, *, reason: str, env: Mapping[str, str]) -> str:
    """One fixture-catalog table row for the release notes (reason sanitized to one cell)."""
    return f"| {ref} | {contents_column(manifest)} | {_sanitize_reason(reason) or '—'} | {minted_by(env)} |"


def insert_catalog_row(body: str, row: str) -> str:
    """Insert *row* at the top of the catalog table (newest first).

    The marker sits ABOVE the table (a comment inside a markdown table would
    terminate it), so the row goes after the first header-separator line
    (`|---`) following the marker. If the marker or separator is missing
    (hand-edited notes), append a fresh catalog section instead.
    """
    if CATALOG_MARKER in body:
        lines = body.splitlines()
        start = next(i for i, line in enumerate(lines) if CATALOG_MARKER in line)
        for i in range(start + 1, len(lines)):
            if lines[i].startswith("|---"):
                return "\n".join(lines[: i + 1] + [row] + lines[i + 1 :])
    return f"{body}\n\n{CATALOG_MARKER}\n| Version | Contents | Why it exists | Minted by |\n|---|---|---|---|\n{row}\n"


def _ensure_release() -> None:
    if release._release_exists():
        return
    release._release_gh(
        "create",
        RELEASE_TAG,
        "--title",
        "Testbed state fixtures",
        "--notes",
        "Immutable testbed state fixtures. Do not delete assets.",
        "--latest=false",
    )


def publish(candidate: Path, *, reason: str | None, env: Mapping[str, str] | None = None) -> str:
    """Mint the next ref, upload the bundle, then edit the release notes with its catalog row.

    ``reason=None`` falls back to the ``REASON`` env var, then the candidate
    manifest. Returns the minted ref; when ``GITHUB_OUTPUT`` is set, also
    writes ``state_ref=<ref>``.

    A failure between the upload and the notes edit leaves an orphaned asset
    with no catalog row; recover by deleting the asset or hand-adding the
    row — a retry mints the next ref, not the orphaned one.
    """
    env = os.environ if env is None else env
    manifest = read_manifest(candidate)
    if reason is None:
        reason = env.get("REASON") or str(manifest.get("reason") or "")
    ref = release.next_ref(release.latest_ref(release._release_asset_names()))
    tarball = candidate.parent / f"{ref}.tar.zst"
    shutil.copy2(candidate, tarball)
    _ensure_release()
    # State refs are immutable: a concurrent publisher must fail on collision,
    # never replace the asset that won the race.
    release._release_gh("upload", RELEASE_TAG, str(tarball))
    body = json.loads(release._release_gh("view", RELEASE_TAG, "--json", "body"))["body"]
    row = catalog_row(ref, manifest, reason=reason, env=env)
    release._release_gh("edit", RELEASE_TAG, "--notes", insert_catalog_row(body, row))
    if env.get("GITHUB_OUTPUT"):
        with open(env["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
            fh.write(f"state_ref={ref}\n")
    print(f"published {ref}")
    return ref
