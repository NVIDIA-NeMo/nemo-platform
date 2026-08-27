# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Bake NMP_PYTHON_IMAGE must match the python-base Dockerfile default."""

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
REVIEWED_PYTHON_IMAGE = "python:3.13.15-slim-trixie"


def _bake_nmp_python_image() -> str:
    """Return the default NMP_PYTHON_IMAGE from docker-bake.hcl."""
    text = (ROOT / "docker-bake.hcl").read_text(encoding="utf-8")
    match = re.search(
        r'variable\s+"NMP_PYTHON_IMAGE"\s*\{[^}]*default\s*=\s*"([^"]+)"',
        text,
        re.DOTALL,
    )
    assert match is not None, "NMP_PYTHON_IMAGE default missing from docker-bake.hcl"
    return match.group(1)


def _dockerfile_nmp_python_image() -> str:
    """Return ARG NMP_PYTHON_IMAGE from the python-base Dockerfile."""
    text = (ROOT / "docker/base/Dockerfile.nmp-python-base").read_text(encoding="utf-8")
    match = re.search(r"^ARG NMP_PYTHON_IMAGE=(.+)$", text, re.MULTILINE)
    assert match is not None, "ARG NMP_PYTHON_IMAGE missing from Dockerfile.nmp-python-base"
    return match.group(1).strip()


def test_bake_python_image_matches_python_base_dockerfile() -> None:
    """Bake must not override python-base back to an older patch release."""
    bake = _bake_nmp_python_image()
    dockerfile = _dockerfile_nmp_python_image()
    assert bake == dockerfile == REVIEWED_PYTHON_IMAGE
