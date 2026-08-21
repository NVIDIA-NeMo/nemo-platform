#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Remove files, symlinks, and directories listed as absolute glob patterns."""

from __future__ import annotations

import argparse
import glob
import os
import shutil
import sys
from collections.abc import Iterable
from pathlib import Path


def read_patterns(list_path: Path) -> list[str]:
    if not list_path.is_file():
        raise FileNotFoundError(f"missing file list: {list_path}")

    patterns: list[str] = []
    for line_number, line in enumerate(list_path.read_text(encoding="utf-8").splitlines(), start=1):
        pattern = line.strip()
        if not pattern or pattern.startswith("#"):
            continue
        if not Path(pattern).is_absolute():
            raise ValueError(f"{list_path}:{line_number}: cleanup path must be absolute: {pattern}")
        patterns.append(pattern)
    return patterns


def remove_target(target: Path) -> None:
    if target.is_dir() and not target.is_symlink():
        shutil.rmtree(target)
    else:
        target.unlink()

    if os.path.lexists(target):
        raise OSError(f"listed path remains after cleanup: {target}")


def remove_patterns(patterns: Iterable[str]) -> list[str]:
    errors: list[str] = []
    for pattern in patterns:
        for target_name in sorted(glob.iglob(pattern, recursive=True)):
            target = Path(target_name)
            try:
                remove_target(target)
            except OSError as exc:
                errors.append(f"failed to remove listed path {target}: {exc}")
    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file_lists", nargs="+", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    all_patterns: list[str] = []
    for list_path in args.file_lists:
        try:
            all_patterns.extend(read_patterns(list_path))
        except (FileNotFoundError, ValueError) as exc:
            print(exc, file=sys.stderr)
            return 1

    errors = remove_patterns(all_patterns)
    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
