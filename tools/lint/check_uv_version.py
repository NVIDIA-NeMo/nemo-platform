#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Ensure uv uses the same version constraint in Flox and pyproject.toml."""

import sys
import tomllib
from collections.abc import Mapping
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT_PATH = PROJECT_ROOT / "pyproject.toml"
FLOX_MANIFEST_PATH = PROJECT_ROOT / "tools/python/.flox/env/manifest.toml"


def load_toml(path: Path) -> dict[str, object]:
    with path.open("rb") as file:
        return tomllib.load(file)


def get_nested_value(config: Mapping[str, object], *keys: str) -> object | None:
    value: object = config
    for key in keys:
        if not isinstance(value, Mapping):
            return None
        value = value.get(key)
    return value


def main() -> int:
    pyproject = load_toml(PYPROJECT_PATH)
    manifest = load_toml(FLOX_MANIFEST_PATH)

    pyproject_version = get_nested_value(pyproject, "tool", "uv", "required-version")
    flox_version = get_nested_value(manifest, "install", "uv", "version")

    if not isinstance(pyproject_version, str) or not isinstance(flox_version, str):
        print("uv version constraints must be strings", file=sys.stderr)
        return 1

    if pyproject_version != flox_version:
        print(
            "uv version constraints differ: "
            f"pyproject.toml has {pyproject_version!r}, while "
            f"tools/python/.flox/env/manifest.toml has {flox_version!r}",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
