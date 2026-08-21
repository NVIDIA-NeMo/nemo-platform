# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared helpers for image file-removal smoke tests."""

from glob import glob
from pathlib import Path


def read_file_patterns(*list_paths: Path) -> list[str]:
    patterns: list[str] = []
    for list_path in list_paths:
        patterns.extend(
            line.strip()
            for line in list_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        )
    return patterns


def assert_file_patterns_absent(patterns: list[str]) -> None:
    remaining = sorted(path for pattern in patterns for path in glob(pattern, recursive=True))
    assert remaining == [], f"file cleanup left scanner-visible files: {remaining}"
