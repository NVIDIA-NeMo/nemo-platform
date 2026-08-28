# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""RL base must copy official CPython 3.13.15 instead of uv python install."""

from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
RL_BASE = ROOT / "docker/rl/Dockerfile.nmp-rl-base"


def test_rl_base_copies_official_cpython_315_and_pins_uv_python() -> None:
    """uv has no linux-gnu 3.13.15 catalog entry; RL must copy official CPython."""
    text = RL_BASE.read_text(encoding="utf-8")
    assert "python:3.13.15-slim-trixie" in text
    assert "COPY --from=cpython /usr/local /opt/cpython" in text
    assert "UV_PYTHON=/opt/cpython/bin/python3.13" in text
    assert 'uv python install "${PYTHON_VERSION}"' not in text
