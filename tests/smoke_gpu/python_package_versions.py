# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared helpers for image package minimum-version smoke tests."""

from importlib import metadata

from packaging.version import Version


def assert_python_package_min_versions(minimum_versions: dict[str, str]) -> None:
    missing: list[str] = []
    too_old: list[str] = []

    for distribution, minimum_version in sorted(minimum_versions.items()):
        try:
            actual_version = metadata.version(distribution)
        except metadata.PackageNotFoundError:
            missing.append(distribution)
            continue

        if Version(actual_version) < Version(minimum_version):
            too_old.append(f"{distribution}: expected >= {minimum_version}, got {actual_version}")

    assert missing == [], f"missing expected Python distributions: {missing}"
    assert too_old == [], "Python distributions below minimum versions: " + "; ".join(too_old)
