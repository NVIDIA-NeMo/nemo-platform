# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Contracts shared by source and container Python runtimes."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_source_bootstrap_matches_container_python_minor() -> None:
    """Cloudpickle payloads require the source and task runtimes to share a minor version."""
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    docker_bake = (REPO_ROOT / "docker-bake.hcl").read_text(encoding="utf-8")
    flox_manifest = (REPO_ROOT / "tools/python/.flox/env/manifest.toml").read_text(encoding="utf-8")

    source_match = re.search(r"^PYTHON_VERSION \?= (\d+\.\d+)$", makefile, re.MULTILINE)
    flox_match = re.search(r'^UV_PYTHON="(\d+\.\d+)"$', flox_manifest, re.MULTILINE)
    image_match = re.search(
        r'variable "NMP_PYTHON_IMAGE"\s*\{\s*default = "python:(\d+\.\d+)(?:\.\d+)?[^\"]*"',
        docker_bake,
        re.MULTILINE,
    )

    assert source_match is not None, "Makefile must declare the default source Python version"
    assert flox_match is not None, "Flox must declare the default source Python version"
    assert image_match is not None, "docker-bake.hcl must declare the default task Python image"
    assert source_match.group(1) == flox_match.group(1)
    assert source_match.group(1) == image_match.group(1)
