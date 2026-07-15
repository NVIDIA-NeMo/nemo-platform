# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for reduced uv workspaces used by Docker image builds."""

import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent
WORKSPACE_SLICES = ("automodel", "rl", "unsloth")


def _load_pyproject(path: Path) -> dict:
    with open(path, "rb") as pyproject:
        return tomllib.load(pyproject)


def _normalize_package_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _workspace_sources(pyproject: dict) -> set[str]:
    sources = pyproject.get("tool", {}).get("uv", {}).get("sources", {})
    return {
        _normalize_package_name(name)
        for name, source in sources.items()
        if isinstance(source, dict) and source.get("workspace") is True
    }


@pytest.mark.parametrize("slice_name", WORKSPACE_SLICES)
def test_docker_workspace_slice_contains_all_workspace_sources(slice_name):
    """Every workspace source must name a package copied into the image slice."""
    workspace_path = ROOT / "docker" / slice_name / "pyproject.workspace.toml"
    workspace = _load_pyproject(workspace_path)
    member_paths = workspace["tool"]["uv"]["workspace"]["members"]
    member_projects = [
        (ROOT / member / "pyproject.toml", _load_pyproject(ROOT / member / "pyproject.toml")) for member in member_paths
    ]
    member_names = {_normalize_package_name(project["project"]["name"]) for _, project in member_projects}

    for project_path, project in [(workspace_path, workspace), *member_projects]:
        missing_sources = _workspace_sources(project) - member_names
        assert not missing_sources, (
            f"{slice_name} workspace is missing {sorted(missing_sources)} referenced by "
            f"{project_path.relative_to(ROOT)}"
        )


def test_deployments_plugin_is_optional_for_models_service():
    """The lazily loaded deployments backend must remain an optional package."""
    models = _load_pyproject(ROOT / "services/core/models/pyproject.toml")
    dependency_names = {
        _normalize_package_name(re.match(r"[A-Za-z0-9_.-]+", dependency).group())
        for dependency in models["project"]["dependencies"]
    }

    assert "nemo-deployments-plugin" not in dependency_names, (
        "nmp-models loads the deployments backend lazily, so nemo-deployments-plugin "
        "must not be an unconditional dependency"
    )
    assert "nemo-deployments-plugin" not in _workspace_sources(models), (
        "an optional package must not be declared as a required workspace source"
    )
