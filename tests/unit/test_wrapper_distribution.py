# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for the published ``nemo-platform`` wrapper distribution."""

import tomllib
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent


def test_all_extra_bundles_default_deployments_backend() -> None:
    """The backend enabled by the packaged config must ship in ``nemo-platform[all]``."""
    pyproject_path = ROOT / "packages/nemo_platform/pyproject.toml"
    with open(pyproject_path, "rb") as pyproject:
        wrapper = tomllib.load(pyproject)

    project = wrapper["project"]
    bundle = wrapper["tool"]["bundle-package"]["nemo-deployments-plugin"]

    assert bundle["inherit"]["entry-points"] == ["nemo.*"]
    assert bundle["module"] == "nemo_deployments_plugin"
    assert (pyproject_path.parent / bundle["source"]).resolve().is_dir()
    assert "nemo-platform[services]" in project["optional-dependencies"]["all"]
    assert "nemo-platform[plugins]" in project["optional-dependencies"]["services"]
    assert "nemo-platform[nemo-deployments-plugin]" in project["optional-dependencies"]["plugins"]
    assert "nemo-deployments-plugin" in project["optional-dependencies"]
    assert project["entry-points"]["nemo.services"]["deployments"].startswith("nemo_deployments_plugin.")
    assert project["entry-points"]["nemo.controllers"]["deployments"].startswith("nemo_deployments_plugin.")
    assert project["entry-points"]["nemo.sandbox_profiles"]["openshell"].startswith("nemo_deployments_plugin.")
    assert project["entry-points"]["nemo.skills"]["deployments"].startswith("nemo_deployments_plugin.")
