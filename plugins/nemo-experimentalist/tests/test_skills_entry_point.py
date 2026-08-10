# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the nemo.skills entry-point exposure."""

from __future__ import annotations

from pathlib import Path


def test_skills_dir_contains_terminator() -> None:
    from nemo_experimentalist_plugin.skills import skills_dir

    terminator = skills_dir() / "terminator"
    assert terminator.is_dir(), (
        f"Expected 'terminator' subdir under {skills_dir()!r} — got {list(skills_dir().iterdir())}"
    )


def test_entry_point_loads_skills_dir() -> None:
    """The nemo.skills entry-point must resolve to our skills_dir function."""
    from importlib.metadata import entry_points

    eps = [ep for ep in entry_points(group="nemo.skills") if ep.name == "experimentalist"]
    assert len(eps) == 1, f"Expected exactly one 'experimentalist' entry-point, got {eps}"
    loaded = eps[0].load()
    assert callable(loaded), f"Entry-point did not resolve to a callable: {loaded!r}"
    result = loaded()
    assert isinstance(result, Path), f"skills_dir() returned {result!r} (not Path)"
    assert result.is_dir(), f"skills_dir() returned {result!r} which is not a directory"
