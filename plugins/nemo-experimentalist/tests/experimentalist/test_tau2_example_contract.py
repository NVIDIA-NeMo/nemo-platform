# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Build-reproducibility contracts for the Tau2 example.

These assert relationships *between* files, never that a pin equals a literal
repeated in the test — that would only restate the constant it is meant to guard.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "tau2-nooa-oo-agent"
_ENVIRONMENT = _EXAMPLE / "dataset" / "template" / "task_template" / "environment"
_DOCKERFILES = (_ENVIRONMENT / "Dockerfile", _ENVIRONMENT / "runtime-server" / "Dockerfile")

# Root pyproject.toml overrides FastMCP to >=3.2.0 for GHSA-vv7q-7jx5-f767 (Critical)
# and GHSA-rww4-4w9c-7733 (High). A container that installs less is a regression the
# repo-level override cannot reach, because pip resolves inside the image.
_MIN_FASTMCP = (3, 2, 0)


def _read(path: Path) -> str:
    assert path.is_file(), f"missing Dockerfile: {path}"
    return path.read_text(encoding="utf-8")


def test_both_images_pin_the_same_tau2_bench_revision() -> None:
    """The task environment and the runtime server must load one tau2-bench.

    They are separate images that talk to each other; a drift between them is a
    benchmark whose two halves disagree, which shows up as unexplained task failures
    rather than as a build error.
    """
    revisions = {}
    for dockerfile in _DOCKERFILES:
        match = re.search(r'ARG TAU2_BENCH_REV="([0-9a-f]{40})"', _read(dockerfile))
        assert match, f"{dockerfile.name} must pin TAU2_BENCH_REV to a full 40-char commit sha"
        revisions[dockerfile] = match.group(1)

    assert len(set(revisions.values())) == 1, f"tau2-bench revisions disagree across images: {revisions}"


@pytest.mark.parametrize("dockerfile", _DOCKERFILES, ids=lambda p: p.parent.name)
def test_images_fetch_a_pinned_revision_rather_than_a_moving_branch(dockerfile: Path) -> None:
    # `git clone --depth=1` cannot check out an arbitrary sha, so a shallow clone
    # silently tracks the default branch however the ARG is written.
    content = _read(dockerfile)
    assert "git clone" not in content, "shallow clone cannot pin a sha; use init + fetch --depth 1"
    assert 'fetch --depth 1 "${TAU2_BENCH_REPO}" "${TAU2_BENCH_REV}"' in content
    assert "checkout --detach FETCH_HEAD" in content


def test_runtime_server_meets_the_repo_fastmcp_security_floor() -> None:
    content = _read(_ENVIRONMENT / "runtime-server" / "Dockerfile")
    match = re.search(r'"fastmcp>=(\d+)\.(\d+)\.(\d+),<(\d+)"', content)
    assert match, "runtime-server must install fastmcp with a lower *and* upper bound"

    floor = tuple(int(part) for part in match.groups()[:3])
    assert floor >= _MIN_FASTMCP, (
        f"fastmcp floor {floor} is below the repo's security minimum {_MIN_FASTMCP} "
        "(GHSA-vv7q-7jx5-f767, GHSA-rww4-4w9c-7733)"
    )


def test_nooa_is_pinned_to_a_commit_not_a_tag() -> None:
    # Tags are mutable: a moved `v0.0.6` would silently change what this example runs.
    content = (_EXAMPLE / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(r'nooa = \{ git = "[^"]+", rev = "[0-9a-f]{40}" \}', content), (
        "nooa must be pinned with rev = <40-char sha>, not tag = ..."
    )
